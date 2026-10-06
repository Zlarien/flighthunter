# Installe une tâche planifiée Windows qui lance FlightHunter toutes les 2 heures.
# Usage : clic droit > "Exécuter avec PowerShell", ou :  ./scripts/schedule_task.ps1
param(
    [int]$IntervalHours = 2,
    [string]$TaskName = "FlightHunter"
)

$ErrorActionPreference = "Stop"
$projectDir = Split-Path -Parent $PSScriptRoot
$python = (Get-Command python).Source

$action  = New-ScheduledTaskAction -Execute $python -Argument "-m flighthunter" -WorkingDirectory $projectDir
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
           -RepetitionInterval (New-TimeSpan -Hours $IntervalHours) `
           -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "Chasseur de vols multi-sources" -Force

Write-Host "Tâche '$TaskName' installée : lancement toutes les $IntervalHours h."
Write-Host "Pour la supprimer : Unregister-ScheduledTask -TaskName $TaskName -Confirm:`$false"
