param(
    [Parameter(Mandatory = $true)][string]$InstanceName,
    [Parameter(Mandatory = $true)][uri]$ServerUrl
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

function Test-ComfyReady {
    try {
        $request = [System.Net.HttpWebRequest]::Create("$($ServerUrl.AbsoluteUri.TrimEnd('/'))/queue")
        $request.Proxy = $null
        $request.Timeout = 500
        $response = $request.GetResponse()
        $response.Close()
        return $true
    } catch {
        return $false
    }
}

$element = [System.Windows.Automation.AutomationElement]
$scope = [System.Windows.Automation.TreeScope]
$buttonType = New-Object System.Windows.Automation.PropertyCondition(
    $element::ControlTypeProperty, [System.Windows.Automation.ControlType]::Button
)
$panelName = New-Object System.Windows.Automation.PropertyCondition(
    $element::NameProperty, ('Comfy Desktop ' + [char]0x2014 + ' Panel')
)
$namePattern = '(^|\s)' + [regex]::Escape($InstanceName) + '(?=\s|$)'
$deadline = [DateTime]::UtcNow.AddSeconds(60)

while ([DateTime]::UtcNow -lt $deadline) {
    if (Test-ComfyReady) { exit 0 }
    $processIds = @(Get-Process -Name 'Comfy Desktop' -ErrorAction SilentlyContinue | ForEach-Object Id)
    $windows = $element::RootElement.FindAll($scope::Children, [System.Windows.Automation.Condition]::TrueCondition)
    foreach ($window in $windows) {
        try {
            if ($processIds -notcontains $window.Current.ProcessId) { continue }
            $panels = $window.FindAll($scope::Descendants, $panelName)
            foreach ($panel in $panels) {
                $cards = @($panel.FindAll($scope::Descendants, $buttonType) | Where-Object {
                    $_.Current.Name -match $namePattern -and
                    $null -ne $_.FindFirst($scope::Descendants, $buttonType)
                })
                if ($cards.Count -ne 1) { continue }
                $action = $cards[0].GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
                $action.Invoke()
                exit 0
            }
        } catch {
            # Loading or switching the window can temporarily invalidate UIA elements.
        }
    }
    Start-Sleep -Milliseconds 750
}
exit 1
