function Resolve-UserDemoRuntimePath {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$RepositoryRoot,
        [string]$RuntimeName = 'user-demo'
    )

    if ($RuntimeName -cnotmatch '^user-demo(?:-[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?)?$') {
        throw 'RuntimeName must be user-demo or a safe user-demo-* name.'
    }

    $repo = [IO.Path]::GetFullPath($RepositoryRoot)
    $runtimeRoot = [IO.Path]::GetFullPath((Join-Path $repo '.runtime'))
    if ([IO.Path]::GetDirectoryName($runtimeRoot) -ine $repo) {
        throw 'The User Demo runtime root must be the repository .runtime directory.'
    }
    if (Test-Path -LiteralPath $runtimeRoot) {
        $rootItem = Get-Item -LiteralPath $runtimeRoot -Force
        if (($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'The repository .runtime directory cannot be a reparse point.'
        }
    }

    $runtime = [IO.Path]::GetFullPath((Join-Path $runtimeRoot $RuntimeName))
    if ([IO.Path]::GetDirectoryName($runtime) -ine $runtimeRoot) {
        throw 'The selected User Demo runtime must be a direct .runtime child.'
    }
    if (Test-Path -LiteralPath $runtime) {
        $runtimeItem = Get-Item -LiteralPath $runtime -Force
        if (($runtimeItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'The selected User Demo runtime cannot be a reparse point.'
        }
    }
    return $runtime
}

Export-ModuleMember -Function Resolve-UserDemoRuntimePath
