# DJ Database & Recovery Tool

Ein leistungsstarkes, in Python geschriebenes Desktop-Werkzeug zur Verwaltung, Konsistenzprüfung und Wiederherstellung von DJ-Musikbibliotheken (MP3) mit einer grafischen Oberfläche im klassischen Winamp-Layout.

## Features
- **Dual Library Management:** Verwaltung und direkter Vergleich von zwei unabhängigen Musikbibliotheken (Bibliothek A als Master, Bibliothek B zum Abgleich).
- **Smarter Delta-Scan:** Schnelle Indizierung durch Dateigrößen- und Pfad-Caching über eine lokale SQLite-Datenbank.
- **Winamp-Style Media Library:** Intuitive Filterung (Künstler -> Alben -> Tracks) mit integrierter Live-Suche und Duplikatsfilter.
- **Robustes Recovery:** Mehrstufiger, fehlertoleranter Abgleich (ID3-Tags und Dateinamen-Mustererkennung) für beschädigte oder umbenannte Tracks auf alten DJ-Sticks.
- **Vorschau & Explorer-Integration:** Direkter Audio-Preview-Player und Sprung in den Windows-Ordner per Button-Klick.
- **Native Drag & Drop Out:** Nahtloses Ziehen von Tracks direkt aus der App in DJ-Software (z.B. Traktor) oder Mediaplayer.
- **MP3val Integration:** Optionale Validierung und Reparatur von MPEG-Stream-Fehlern.
- **Datenbank-Wartung:** Sichern, Wiederherstellen und Bereinigen der SQLite-Datenbank direkt über die UI.

## Systemvoraussetzungen
- **Python Version:** 3.14 (oder kompatible 3.x Versionen)
- **Betriebssystem:** Windows (aufgrund von `os.startfile` und Windows-spezifischen OLE-Schnittstellen für Drag & Drop).

## Installation & Einrichtung

1. **Repository klonen oder herunterladen:**
   ```bash
   git clone [https://github.com/dein-benutzername/dj-database-tool.git](https://github.com/dein-benutzername/dj-database-tool.git)
   cd dj-database-tool
   
2. **Virtuelle Umgebung erstellen und aktivieren (empfohlen):**

   ```bash
    python -m venv .venv
    .venv\Scripts\activate

3. **Abhängigkeiten installieren:**
Installiere die benötigten Python-Pakete über die requirements.txt:

   ```bash
    pip install -r requirements.txt

4. **Optional (MP3val Unterstützung):**
Aus lizenzrechtlichen Gründen ist das Tool mp3val nicht im Repository enthalten.

Lade die mp3val.exe von der offiziellen Projektseite herunter.

Erstelle im Hauptverzeichnis des Repositories einen Ordner namens mp3val.

Kopiere die mp3val.exe in diesen Ordner (./mp3val/mp3val.exe).

5. **Anwendung starten**
   ```bash
    python dj_recovery_tool.py
   
### Als .exe kompilieren (Standalone)
Um das Tool ohne Python-Installation auf anderen Windows-Computern auszuführen, kann es mit PyInstaller als ausführbare Datei gepackt werden:

Die fertige .exe befindet sich anschließend im Ordner dist/.

   ```bash
    pyinstaller --noconfirm --windowed --add-data "mp3val;mp3val" --collect-data tkinterdnd2 dj_recovery_tool.py

