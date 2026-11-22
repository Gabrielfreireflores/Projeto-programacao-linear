"""Resolve o Problema 1 e exporta o cronograma e os indicadores."""

import argparse
import csv
import os
from itertools import combinations
from pathlib import Path

import gurobipy as gp
from gurobipy import GRB


TIME_LIMIT = 3600


def ler_instancia(caminho):
    with caminho.open(encoding="utf-8-sig", newline="") as arquivo:
        leitor = csv.DictReader(arquivo)
        if leitor.fieldnames != ["tarefa", "p1", "p2", "p3"]:
            raise ValueError(f"{caminho}: cabeçalho esperado: tarefa,p1,p2,p3")
        tarefas = {}
        for linha in leitor:
            nome = (linha["tarefa"] or "").strip()
            try:
                tempos = tuple(int(linha[campo]) for campo in ("p1", "p2", "p3"))
            except (ValueError, TypeError):
                raise ValueError(f"{caminho}:{leitor.line_num}: tempos inteiros esperados") from None
            if not nome or nome in tarefas or None in linha or min(tempos) <= 0:
                raise ValueError(f"{caminho}:{leitor.line_num}: use ID único e tempos positivos")
            tarefas[nome] = tempos
    if not tarefas:
        raise ValueError(f"{caminho}: nenhuma tarefa")
    return tarefas


def atraso_minimo(a, b):
    return max(a[0], a[0] + a[1] - b[0])


def programar_ordem(tempos, ordem):
    inicio_1 = fim_3 = 0
    anterior = None
    cronograma = {}
    for i in ordem:
        p1, p2, p3 = tempos[i]
        if anterior is not None:
            inicio_1 += atraso_minimo(tempos[anterior], tempos[i])
        inicio_3 = max(fim_3, inicio_1 + p1 + p2)
        fim_3 = inicio_3 + p3
        cronograma[i] = inicio_1, inicio_3
        anterior = i
    return cronograma, fim_3


def resolver(tarefas):
    nomes = list(tarefas)
    tempos = list(tarefas.values())
    indices = range(len(tempos))
    inicial, horizonte = programar_ordem(tempos, indices)
    limite_inferior = max(sum(p[k] for p in tempos) for k in range(3))
    with gp.Env(params={"OutputFlag": 0}) as ambiente, gp.Model(
        "flowshop_problema_1", env=ambiente
    ) as modelo:
        modelo.Params.TimeLimit = TIME_LIMIT
        modelo.Params.MIPGap = 0
        modelo.Params.MIPGapAbs = 0
        s = modelo.addVars(indices, ub=horizonte, name="inicio_m1")
        t = modelo.addVars(indices, ub=horizonte, name="inicio_m3")
        c = modelo.addVar(lb=limite_inferior, ub=horizonte, name="makespan")
        c.Start = horizonte
        for i, (p1, p2, p3) in enumerate(tempos):
            modelo.addConstr(t[i] >= s[i] + p1 + p2, name=f"fluxo_{i}")
            modelo.addConstr(c >= t[i] + p3, name=f"fim_{i}")
            s[i].Start, t[i].Start = inicial[i]

        for i, j in combinations(indices, 2):
            antes = modelo.addVar(vtype=GRB.BINARY, name=f"antes_{i}_{j}")
            antes.Start = 1
            for a, b, valor in ((i, j, 1), (j, i, 0)):
                modelo.addGenConstrIndicator(
                    antes, valor, s[b] >= s[a] + atraso_minimo(tempos[a], tempos[b])
                )
                modelo.addGenConstrIndicator(antes, valor, t[b] >= t[a] + tempos[a][2])

        modelo.setObjective(c, GRB.MINIMIZE)
        modelo.optimize()
        status = {GRB.OPTIMAL: "OTIMO", GRB.TIME_LIMIT: "LIMITE_TEMPO"}
        gap = ""
        if modelo.SolCount and modelo.IsMIP:
            gap = 100 * modelo.MIPGap
        elif modelo.Status == GRB.OPTIMAL:
            gap = 0
        resultado = {
            "tarefas": len(tempos),
            "status": status.get(modelo.Status, f"GUROBI_{modelo.Status}"),
            "objetivo": modelo.ObjVal if modelo.SolCount else "",
            "limitante": modelo.ObjBound,
            "gap_percentual": gap,
            "tempo_segundos": modelo.Runtime,
        }
        dados_brutos = {
            "status": modelo.Status,
            "solucoes": modelo.SolCount,
            "tarefas": nomes,
            "variaveis": [],
        }
        cronograma = []
        if modelo.SolCount:
            dados_brutos["variaveis"] = [
                (variavel.VarName, variavel.X) for variavel in modelo.getVars()
            ]
            ordem = sorted(indices, key=lambda i: s[i].X)
            # Reconstrói horários inteiros e elimina folgas do incumbente.
            horarios, _ = programar_ordem(tempos, ordem)
            for i in ordem:
                inicio_1, inicio_3 = horarios[i]
                p1, p2, p3 = tempos[i]
                cronograma.append((
                    nomes[i], inicio_1, inicio_1 + p1, inicio_1 + p1,
                    inicio_1 + p1 + p2, inicio_3, inicio_3 + p3,
                ))
    return resultado, cronograma, dados_brutos


def exibir_resultado(instancia, resultado, cronograma):
    def formatar(valor, sufixo="", casas=3):
        if valor == "":
            return "indisponível"
        if 0 < valor < 10 ** -casas:
            return "< " + f"{10 ** -casas:.{casas}f}".replace(".", ",") + sufixo
        texto = f"{valor:.{casas}f}".rstrip("0").rstrip(".").replace(".", ",")
        return texto + sufixo

    status = resultado["status"]
    mensagem = {
        "OTIMO": "Ótimo comprovado pelo Gurobi.",
        "LIMITE_TEMPO": "Limite de tempo atingido.",
    }.get(status, f"O Gurobi encerrou com o código {status.removeprefix('GUROBI_')}.")
    rotulo_objetivo = "Valor ótimo (makespan)" if status == "OTIMO" else "Melhor valor encontrado"
    campos = [
        ("Instância", instancia),
        ("Quantidade de tarefas", resultado["tarefas"]),
        ("Situação", mensagem),
        (rotulo_objetivo, formatar(resultado["objetivo"], " unidades de tempo")),
        ("Limitante inferior", formatar(resultado["limitante"], " unidades de tempo")),
        ("Gap de otimalidade", formatar(resultado["gap_percentual"], "%")),
        ("Tempo no Gurobi", formatar(resultado["tempo_segundos"], " s")),
        ("Limite por instância", f"{TIME_LIMIT} s"),
    ]
    if cronograma:
        campos.append(("Sequência das tarefas", " → ".join(linha[0] for linha in cronograma)))
        campos.append(("Fim do cronograma", f"{cronograma[-1][-1]} unidades de tempo"))
    largura = max(len(rotulo) for rotulo, _ in campos)
    print("\nPROBLEMA 1 | RESULTADO DA OTIMIZAÇÃO")
    for rotulo, valor in campos:
        print(f"  {rotulo:<{largura}}  {valor}")

    if not cronograma:
        print("\nO solver não retornou uma programação viável.")
        return

    print("\nCronograma (início–fim)")
    cabecalho = ("Tarefa", "Máquina 1", "Máquina 2", "Máquina 3")
    linhas = [cabecalho] + [
        (nome, f"{a}–{b}", f"{c}–{d}", f"{e}–{f}")
        for nome, a, b, c, d, e, f in cronograma
    ]
    larguras = [max(map(len, coluna)) for coluna in zip(*linhas)]
    for tarefa, *maquinas in linhas:
        intervalos = "  ".join(f"{v:>{w}}" for v, w in zip(maquinas, larguras[1:]))
        print(f"  {tarefa:<{larguras[0]}}  {intervalos}")
    print("\nPara cada tarefa, o fim na máquina 1 coincide com o início na máquina 2.")
    if status == "OTIMO":
        print("O limitante inferior confirma que nenhum cronograma termina antes.")
    elif status == "LIMITE_TEMPO":
        print("O gap mede a distância relativa entre a solução do Gurobi e o limitante.")


def exibir_dados_brutos(resultado, dados_brutos):
    print("\nDADOS BRUTOS DO GUROBI")
    print(f"  Status = {dados_brutos['status']}")
    print(f"  SolCount = {dados_brutos['solucoes']}")
    print(f"  ObjBound = {resultado['limitante']!r}")
    print(f"  Runtime = {resultado['tempo_segundos']!r}")
    if not dados_brutos["solucoes"]:
        print("  Valores das variáveis indisponíveis sem uma solução viável.")
        return

    print(f"  ObjVal = {resultado['objetivo']!r}")
    print("\n  Índice → tarefa")
    for indice, nome in enumerate(dados_brutos["tarefas"]):
        print(f"    {indice} → {nome}")
    print("\n  Variáveis (valores do solver, antes de recalcular o cronograma)")
    print("    inicio_m1[i] e inicio_m3[i]: horários de início da tarefa i")
    print("    antes_i_j: 1 se i precede j, 0 se j precede i")
    print("    makespan: horário de término do lote")
    for nome, valor in dados_brutos["variaveis"]:
        print(f"    {nome} = {valor!r}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("instancias", nargs="*", type=Path,
                        help="arquivos CSV (sem argumentos, executa o exemplo)")
    parser.add_argument("--saida", type=Path, default=Path("resultados"))
    args = parser.parse_args()
    caminhos = args.instancias or [Path(__file__).with_name("exemplo.csv")]
    licenca = Path.home() / "Downloads" / "gurobi.lic"
    if not os.environ.get("GRB_LICENSE_FILE") and licenca.is_file():
        os.environ["GRB_LICENSE_FILE"] = str(licenca)
    if len({p.stem.casefold() for p in caminhos}) != len(caminhos):
        parser.error("use nomes de arquivo distintos para as instâncias")
    args.saida.mkdir(parents=True, exist_ok=True)
    campos = ["instancia", "tarefas", "status", "objetivo", "limitante",
              "gap_percentual", "tempo_segundos"]
    with (args.saida / "resumo.csv").open("w", newline="", encoding="utf-8") as arquivo:
        resumo = csv.DictWriter(arquivo, fieldnames=campos)
        resumo.writeheader()
        for caminho in caminhos:
            try:
                resultado, cronograma, dados_brutos = resolver(ler_instancia(caminho))
            except (OSError, ValueError, gp.GurobiError) as erro:
                parser.exit(1, f"{caminho}: {erro}\n")
            with (args.saida / f"{caminho.stem}_cronograma.csv").open(
                "w", newline="", encoding="utf-8"
            ) as arquivo_cronograma:
                tabela = csv.writer(arquivo_cronograma)
                tabela.writerow(("tarefa", "inicio_m1", "fim_m1", "inicio_m2",
                                 "fim_m2", "inicio_m3", "fim_m3"))
                tabela.writerows(cronograma)
            resumo.writerow({"instancia": caminho.name, **resultado})
            arquivo.flush()
            exibir_resultado(caminho.name, resultado, cronograma)
            exibir_dados_brutos(resultado, dados_brutos)
    print(f"\nArquivos CSV gravados em: {args.saida}")


if __name__ == "__main__":
    main()
