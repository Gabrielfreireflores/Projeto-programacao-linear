$licencaAnterior = $env:GRB_LICENSE_FILE
if (-not $licencaAnterior) {
    $env:GRB_LICENSE_FILE = Join-Path $env:USERPROFILE 'Downloads\gurobi.lic'
}

try {
    if (-not (Test-Path -LiteralPath $env:GRB_LICENSE_FILE -PathType Leaf)) {
        throw "Arquivo de licença não encontrado em $env:GRB_LICENSE_FILE"
    }
    & python (Join-Path $PSScriptRoot 'optimize.py') @args
    exit $LASTEXITCODE
}
finally {
    $env:GRB_LICENSE_FILE = $licencaAnterior
}
