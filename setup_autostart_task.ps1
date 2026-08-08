$pythonExe = (Get-Command python).Source
$workingDir = "C:\Users\cscav\OneDrive\Desktop\Antigravity\nse_oc"
$scriptPath = "$workingDir\background_runner.py"

# Scheduled Task Action
$action = New-ScheduledTaskAction -Execute $pythonExe -Argument $scriptPath -WorkingDirectory $workingDir

# Mon-Fri 8:55 AM Trigger
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "08:55AM"

# Task Settings: Run whether user is logged on or not, wake computer if sleeping
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 8)

Register-ScheduledTask -TaskName "TrendingOI_AutoStart_855AM" -Action $action -Trigger $trigger -Settings $settings -Description "Auto-start Trending OI background daemon Mon-Fri at 8:55 AM" -Force

Write-Host "✅ Scheduled Task 'TrendingOI_AutoStart_855AM' created successfully!"
