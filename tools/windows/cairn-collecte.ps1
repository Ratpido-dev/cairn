<#
    Collecte des journaux Hearthstone sous Windows, pour Cairn.

    Hearthstone ne garde qu'une poignée de dossiers de session : ce qui n'est
    pas copié le jour même est perdu. Ce script archive chaque session en un
    .zip, et ne garde que les deux journaux utiles au tracker :

        Power.log   tous les événements de jeu   (~15 Mo, mais ×18 à la compression)
        Decks.log   noms et deckstrings des decks (~2 Ko)

    Il est fait pour tourner en boucle (tâche planifiée) : il ne recopie que
    ce qui a changé, et sait lire les fichiers pendant que le jeu écrit dedans.

    Usage :
        .\cairn-collecte.ps1                 archive dans Documents\cairn-parties
        .\cairn-collecte.ps1 -Liste          montre ce qui serait fait, sans écrire
        .\cairn-collecte.ps1 -Dest D:\parties -LogsPath "C:\Jeux\Hearthstone\Logs"
        .\cairn-collecte.ps1 -Installer      pose la tâche planifiée (une fois)
        .\cairn-collecte.ps1 -Verifier      dit si la collecte tourne vraiment
        .\cairn-collecte.ps1 -Desinstaller   retire la tâche planifiée
#>

[CmdletBinding()]
param(
    [string] $LogsPath,
    [string] $Dest = (Join-Path $env:USERPROFILE "Documents\cairn-parties"),
    [switch] $Liste,         # essai à blanc : n'écrit rien
    [switch] $Installer,     # enregistre la tâche planifiée
    [switch] $Desinstaller,  # retire la tâche planifiée
    [switch] $Verifier       # dit si la collecte tourne, et où elle écrit
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

$FICHIERS = @("Power.log", "Decks.log")
$TACHE = "Cairn - collecte"
# Set-StrictMode fait échouer la lecture d'une variable jamais définie : on la
# déclare ici plutôt que de compter sur Installer-Tache pour l'avoir remplie.
$script:DestinationTache = $null


function Installer-Tache {
    <# Pose la tâche planifiée, pour de bon.

       On n'utilise PAS « schtasks /sc minute », dont les réglages par défaut
       sont des pièges sur un portable : il refuse de démarrer sur batterie,
       s'arrête si la machine y bascule, et ne rattrape jamais une occurrence
       manquée pendant que le PC était éteint. On enregistre donc la tâche
       explicitement, avec :

         · un déclencheur à l'OUVERTURE DE SESSION — au redémarrage, la
           collecte tourne avant que le joueur ne relance Hearthstone (et donc
           avant que le jeu n'efface les vieux dossiers de journaux) ;
         · une répétition toutes les 20 minutes pendant qu'il joue ;
         · le rattrapage des occurrences manquées ;
         · aucune condition d'alimentation.
    #>
    # Le joueur, PAS le compte qui installe. Si l'installation passe par « Exécuter
    # en tant qu'administrateur » avec un AUTRE compte, tout enregistrer sous ce
    # compte-là serait un piège silencieux : le déclencheur à l'ouverture de
    # session ne partirait jamais pour le joueur, et les archives atterriraient
    # dans le Documents de l'administrateur.
    $joueur = (Get-CimInstance Win32_ComputerSystem).UserName   # DOMAINE\utilisateur
    if (-not $joueur) { $joueur = "$env:USERDOMAIN\$env:USERNAME" }

    if ($joueur -ne "$env:USERDOMAIN\$env:USERNAME") {
        Write-Host ("Installation lancée sous {0}\{1}, mais la session ouverte est {2}." -f `
            $env:USERDOMAIN, $env:USERNAME, $joueur) -ForegroundColor Yellow
        Write-Host "La tâche sera posée pour $joueur — c'est bien lui qui joue." `
            -ForegroundColor Yellow
    }

    # Destination résolue pour LE JOUEUR. On ne fige pas $env:USERPROFILE du
    # compte installateur, qui serait le mauvais dossier.
    $destination = $Dest
    if (-not $PSBoundParameters.ContainsKey('Dest')) {
        $sid = (New-Object System.Security.Principal.NTAccount($joueur)).Translate(
                   [System.Security.Principal.SecurityIdentifier]).Value
        $profil = (Get-ItemProperty ("HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion" +
                                     "\ProfileList\$sid") -ErrorAction SilentlyContinue).ProfileImagePath
        if ($profil) { $destination = Join-Path $profil "Documents\cairn-parties" }
    }

    $script = $PSCommandPath
    $arguments = ('-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass ' +
                  '-File "{0}" -Dest "{1}"' -f $script, $destination)

    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments
    $identite = New-ScheduledTaskPrincipal -UserId $joueur -LogonType Interactive

    $auDemarrage = New-ScheduledTaskTrigger -AtLogOn
    $repetition  = New-ScheduledTaskTrigger -Once -At (Get-Date) `
        -RepetitionInterval (New-TimeSpan -Minutes 20) `
        -RepetitionDuration (New-TimeSpan -Days 3650)

    $reglages = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

    Register-ScheduledTask -TaskName $TACHE -Action $action `
        -Trigger $auDemarrage, $repetition -Settings $reglages -Principal $identite `
        -Description "Archive les journaux Hearthstone avant que le jeu ne les efface." `
        -Force | Out-Null

    Write-Host "Tâche « $TACHE » enregistrée." -ForegroundColor Green
    Write-Host "  · pour le compte : $joueur"
    Write-Host "  · à l'ouverture de sa session Windows"
    Write-Host "  · puis toutes les 20 minutes"
    Write-Host "  · sur secteur comme sur batterie"
    Write-Host "  · destination : $destination"

    $script:DestinationTache = $destination
}


function Verifier-Tache {
    <# Dit en clair si la collecte est réellement en place et où elle écrit. #>
    $t = Get-ScheduledTask -TaskName $TACHE -ErrorAction SilentlyContinue
    if (-not $t) {
        Write-Host "Aucune tâche « $TACHE » : la collecte n'est PAS installée." `
            -ForegroundColor Red
        Write-Host "Double-clique sur Installer-la-collecte-auto.bat."
        return
    }
    $info = Get-ScheduledTaskInfo -TaskName $TACHE
    $cible = if ($t.Actions.Arguments -match '-Dest "([^"]+)"') { $Matches[1] } else { "?" }

    Write-Host "Tâche installée." -ForegroundColor Green
    Write-Host "  compte         : $($t.Principal.UserId)"
    Write-Host "  session ouverte: $((Get-CimInstance Win32_ComputerSystem).UserName)"
    Write-Host "  écrit dans     : $cible"
    Write-Host "  dernier passage: $($info.LastRunTime)  (code $($info.LastTaskResult))"

    if ($t.Principal.UserId -notlike "*$env:USERNAME") {
        Write-Host ("ATTENTION : la tâche tourne sous un autre compte que la session " +
                    "ouverte. Relance Installer-la-collecte-auto.bat.") -ForegroundColor Red
    }
    if (Test-Path -LiteralPath $cible) {
        $n = (Get-ChildItem -LiteralPath $cible -Filter *.zip -ErrorAction SilentlyContinue).Count
        Write-Host "  parties déjà archivées : $n" -ForegroundColor Green
    } else {
        Write-Host "  (rien encore archivé — normal avant la première partie)"
    }
}


function Desinstaller-Tache {
    if (Get-ScheduledTask -TaskName $TACHE -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TACHE -Confirm:$false
        Write-Host "Tâche « $TACHE » retirée." -ForegroundColor Green
    } else {
        Write-Host "Aucune tâche « $TACHE » à retirer."
    }
    Write-Host "Les parties déjà archivées ne sont pas touchées."
}


function Trouver-Logs {
    <# Dossier Logs\ du jeu : paramètre, puis registre, puis emplacements usuels. #>
    if ($LogsPath) {
        if (-not (Test-Path -LiteralPath $LogsPath)) {
            throw "Dossier introuvable : $LogsPath"
        }
        return (Resolve-Path -LiteralPath $LogsPath).Path
    }

    $cles = @(
        "HKLM:\SOFTWARE\WOW6432Node\Blizzard Entertainment\Hearthstone",
        "HKLM:\SOFTWARE\Blizzard Entertainment\Hearthstone"
    )
    foreach ($cle in $cles) {
        try {
            $install = (Get-ItemProperty -Path $cle -ErrorAction Stop).InstallLocation
            if ($install) {
                $chemin = Join-Path $install "Logs"
                if (Test-Path -LiteralPath $chemin) { return $chemin }
            }
        } catch { }
    }

    $candidats = @(
        "C:\Program Files (x86)\Hearthstone\Logs",
        "C:\Program Files\Hearthstone\Logs",
        "D:\Hearthstone\Logs",
        "C:\Games\Hearthstone\Logs"
    )
    foreach ($c in $candidats) {
        if (Test-Path -LiteralPath $c) { return $c }
    }

    throw ("Dossier Logs de Hearthstone introuvable. Relance avec -LogsPath, " +
           "par exemple : .\cairn-collecte.ps1 -LogsPath ""C:\...\Hearthstone\Logs""")
}


function Copier-Fichier-Ouvert {
    <# Copie un fichier que Hearthstone est peut-être en train d'écrire.

       Copy-Item échoue sur un fichier verrouillé ; on ouvre donc explicitement
       en lecture avec partage ReadWrite, ce que le jeu autorise. #>
    param([string] $Source, [string] $Cible)

    $flux = [System.IO.File]::Open(
        $Source,
        [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Read,
        [System.IO.FileShare]::ReadWrite
    )
    try {
        $sortie = [System.IO.File]::Create($Cible)
        try { $flux.CopyTo($sortie) } finally { $sortie.Dispose() }
    } finally { $flux.Dispose() }
}


function Empreinte-Session {
    <# Signature bon marché d'une session : taille de chaque journal.

       Power.log ne fait que grossir pendant la session ; comparer les tailles
       suffit à savoir si la partie a avancé depuis la dernière archive, sans
       relire 15 Mo à chaque passage. #>
    param([string] $Dossier)

    $bouts = foreach ($nom in $FICHIERS) {
        $f = Join-Path $Dossier $nom
        if (Test-Path -LiteralPath $f) {
            "{0}:{1}" -f $nom, (Get-Item -LiteralPath $f).Length
        }
    }
    return ($bouts -join "|")
}


# ---------------------------------------------------------------- exécution --

if ($Desinstaller) { Desinstaller-Tache; exit 0 }
if ($Verifier)     { Verifier-Tache;     exit 0 }

if ($Installer) {
    Installer-Tache
    if ($script:DestinationTache) { $Dest = $script:DestinationTache }
    Write-Host ""
    Write-Host "Première collecte, tout de suite :"
}

$logs = Trouver-Logs
Write-Host "Journaux du jeu : $logs"

if (-not $Liste -and -not (Test-Path -LiteralPath $Dest)) {
    New-Item -ItemType Directory -Path $Dest -Force | Out-Null
}
Write-Host "Archive         : $Dest"
if ($Liste) { Write-Host "(essai à blanc — rien ne sera écrit)" -ForegroundColor Yellow }

$indexPath = Join-Path $Dest ".index.json"
$index = @{}
if (-not $Liste -and (Test-Path -LiteralPath $indexPath)) {
    try {
        $brut = Get-Content -LiteralPath $indexPath -Raw | ConvertFrom-Json
        foreach ($p in $brut.PSObject.Properties) { $index[$p.Name] = $p.Value }
    } catch {
        Write-Host "Index illisible, il sera reconstruit." -ForegroundColor Yellow
    }
}

$sessions = Get-ChildItem -LiteralPath $logs -Directory -Filter "Hearthstone_*" |
            Sort-Object Name
if (-not $sessions) {
    Write-Host "Aucune session trouvée. Hearthstone a-t-il tourné au moins une fois ?" `
        -ForegroundColor Yellow
    exit 0
}

$nouvelles = 0; $majs = 0; $inchangees = 0; $octets = 0

foreach ($s in $sessions) {
    $power = Join-Path $s.FullName "Power.log"
    if (-not (Test-Path -LiteralPath $power)) { continue }   # session sans jeu

    $empreinte = Empreinte-Session $s.FullName
    $zip = Join-Path $Dest ("{0}.zip" -f $s.Name)
    $connue = $index.ContainsKey($s.Name) -and $index[$s.Name] -eq $empreinte

    if ($connue -and (Test-Path -LiteralPath $zip)) {
        $inchangees++
        continue
    }

    $etat = if (Test-Path -LiteralPath $zip) { "mise à jour" } else { "nouvelle" }
    $taille = (Get-Item -LiteralPath $power).Length / 1MB
    Write-Host ("  {0,-34} {1,-12} {2,6:N1} Mo" -f $s.Name, $etat, $taille)

    if ($Liste) {
        if ($etat -eq "nouvelle") { $nouvelles++ } else { $majs++ }
        continue
    }

    # On copie d'abord dans un dossier temporaire : Compress-Archive ne sait
    # pas lire un fichier que le jeu tient ouvert.
    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("cairn-" + [guid]::NewGuid())
    New-Item -ItemType Directory -Path $tmp -Force | Out-Null
    try {
        foreach ($nom in $FICHIERS) {
            $src = Join-Path $s.FullName $nom
            if (Test-Path -LiteralPath $src) {
                Copier-Fichier-Ouvert $src (Join-Path $tmp $nom)
            }
        }
        Compress-Archive -Path (Join-Path $tmp "*") -DestinationPath $zip `
                         -CompressionLevel Optimal -Force
        $index[$s.Name] = $empreinte
        $octets += (Get-Item -LiteralPath $zip).Length
        if ($etat -eq "nouvelle") { $nouvelles++ } else { $majs++ }
    } catch {
        Write-Host ("    échec : {0}" -f $_.Exception.Message) -ForegroundColor Red
    } finally {
        Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

if (-not $Liste) {
    $index | ConvertTo-Json | Set-Content -LiteralPath $indexPath -Encoding UTF8
}

$total = (Get-ChildItem -LiteralPath $Dest -Filter "*.zip" -ErrorAction SilentlyContinue |
          Measure-Object -Property Length -Sum).Sum
Write-Host ""
Write-Host ("{0} nouvelle(s), {1} mise(s) à jour, {2} inchangée(s)" -f `
    $nouvelles, $majs, $inchangees) -ForegroundColor Green
if ($total) {
    Write-Host ("Archive totale : {0:N1} Mo dans {1}" -f ($total / 1MB), $Dest)
}
