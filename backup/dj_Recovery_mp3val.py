import sqlite3
import os
import shutil
import subprocess
import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from tinytag import TinyTag
except ImportError:
    messagebox.showerror("Fehler", "Das Modul 'tinytag' fehlt.\nBitte mit 'pip install tinytag' installieren.")
    exit(1)

DB_FILE = "dj_library.db"
SETTINGS_FILE = "dj_settings.json"


def format_length(seconds):
    if not seconds: return "0:00"
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}:{secs:02d}"


class DJRecoveryApp:
    def __init__(self, root):
        self.root = root
        self.root.title("DJ Database Tool - Smart Edition + MP3val")
        self.root.geometry("1400x800")

        self.mp3val_path = Path(__file__).parent / "mp3val" / "mp3val.exe"

        # Standard-Einstellungen initialisieren
        self.settings = {
            "library_folders": [],
            "stick_path": r"M:\Stick_Backup"
        }
        self.load_settings()

        self.init_db()
        self.create_gui()

    def init_db(self):
        self.conn = sqlite3.connect(DB_FILE)
        self.cursor = self.conn.cursor()

        self.cursor.execute('''
                            CREATE TABLE IF NOT EXISTS tracks
                            (
                                id
                                INTEGER
                                PRIMARY
                                KEY
                                AUTOINCREMENT,
                                filepath
                                TEXT
                                UNIQUE,
                                filename
                                TEXT,
                                artist
                                TEXT,
                                title
                                TEXT,
                                album
                                TEXT,
                                genre
                                TEXT,
                                year
                                TEXT,
                                track_num
                                TEXT,
                                duration
                                REAL,
                                filesize
                                INTEGER,
                                bitrate
                                REAL,
                                samplerate
                                INTEGER
                            )
                            ''')
        self.conn.commit()

    # --- NEU: JSON Einstellungs-Manager ---
    def load_settings(self):
        if Path(SETTINGS_FILE).exists():
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    loaded_data = json.load(f)
                    self.settings.update(loaded_data)
            except Exception as e:
                print(f"Fehler beim Laden der Einstellungen: {e}")

    def save_settings(self, *args):
        # Wird getriggert, sobald Listen oder Pfade in der GUI existieren und geändert werden
        if hasattr(self, 'lib_listbox') and hasattr(self, 'stick_path_var'):
            self.settings["library_folders"] = list(self.lib_listbox.get(0, tk.END))
            self.settings["stick_path"] = self.stick_path_var.get()
            try:
                with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                    json.dump(self.settings, f, indent=4)
            except Exception as e:
                print(f"Fehler beim Speichern der Einstellungen: {e}")

    # --- HILFSFUNKTIONEN FÜR SORTIERUNG & VORSCHAU ---
    def sort_column(self, tv, col, reverse):
        l = [(tv.set(k, col), k) for k in tv.get_children('')]
        try:
            l.sort(key=lambda t: float(t[0] or 0), reverse=reverse)
        except ValueError:
            l.sort(key=lambda t: str(t[0]).lower(), reverse=reverse)
        for index, (val, k) in enumerate(l):
            tv.move(k, '', index)
        tv.heading(col, command=lambda: self.sort_column(tv, col, not reverse))

    def make_tree_sortable(self, tree, columns):
        for col in columns:
            if col not in ["preview", "check"]:
                tree.heading(col, command=lambda c=col, tv=tree: self.sort_column(tv, c, False))

    def bind_preview(self, tree, action_col_id, path_col_name):
        def on_click(event):
            region = tree.identify("region", event.x, event.y)
            if region == "cell" and tree.identify_column(event.x) == action_col_id:
                item = tree.identify_row(event.y)
                if item:
                    filepath = tree.set(item, path_col_name)
                    try:
                        if Path(filepath).exists():
                            os.startfile(filepath)
                    except:
                        pass

        tree.bind('<ButtonRelease-1>', on_click, add='+')

    def create_gui(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True, padx=5, pady=5)

        self.tab_library = ttk.Frame(notebook)
        notebook.add(self.tab_library, text='Media Library')
        self.setup_library_tab()

        self.tab_settings = ttk.Frame(notebook)
        notebook.add(self.tab_settings, text='Einstellungen & Recovery')
        self.setup_settings_tab()

    def setup_library_tab(self):
        view_frame = ttk.Frame(self.tab_library)
        view_frame.pack(fill='x', padx=5, pady=5)

        ttk.Label(view_frame, text="Ansicht / Gruppierung:").pack(side='left', padx=5)
        self.grouping_var = tk.StringVar(value="artist_album")
        ttk.Radiobutton(view_frame, text="Künstler -> Alben", variable=self.grouping_var, value="artist_album",
                        command=self.update_grouping_mode).pack(side='left', padx=10)
        ttk.Radiobutton(view_frame, text="Alben -> Künstler", variable=self.grouping_var, value="album_artist",
                        command=self.update_grouping_mode).pack(side='left', padx=10)

        main_paned = ttk.PanedWindow(self.tab_library, orient=tk.HORIZONTAL)
        main_paned.pack(fill='both', expand=True, padx=5, pady=5)

        winamp_paned = ttk.PanedWindow(main_paned, orient=tk.VERTICAL)
        main_paned.add(winamp_paned, weight=4)

        top_split = ttk.PanedWindow(winamp_paned, orient=tk.HORIZONTAL)
        winamp_paned.add(top_split, weight=1)

        self.left_frame = ttk.LabelFrame(top_split, text="Künstler")
        top_split.add(self.left_frame, weight=1)
        self.left_tree = ttk.Treeview(self.left_frame, columns=("item",), show='headings', selectmode='browse')
        self.left_tree.heading("item", text="Alle Künstler")
        self.make_tree_sortable(self.left_tree, ("item",))
        left_scroll = ttk.Scrollbar(self.left_frame, orient="vertical", command=self.left_tree.yview)
        self.left_tree.configure(yscrollcommand=left_scroll.set)
        self.left_tree.pack(side='left', fill='both', expand=True)
        left_scroll.pack(side='right', fill='y')
        self.left_tree.bind('<<TreeviewSelect>>', self.on_left_select)

        self.right_frame = ttk.LabelFrame(top_split, text="Alben")
        top_split.add(self.right_frame, weight=1)
        self.right_tree = ttk.Treeview(self.right_frame, columns=("item",), show='headings', selectmode='browse')
        self.right_tree.heading("item", text="Alle Alben")
        self.make_tree_sortable(self.right_tree, ("item",))
        right_scroll = ttk.Scrollbar(self.right_frame, orient="vertical", command=self.right_tree.yview)
        self.right_tree.configure(yscrollcommand=right_scroll.set)
        self.right_tree.pack(side='left', fill='both', expand=True)
        right_scroll.pack(side='right', fill='y')
        self.right_tree.bind('<<TreeviewSelect>>', self.on_right_select)

        track_frame = ttk.LabelFrame(winamp_paned, text="Tracks")
        winamp_paned.add(track_frame, weight=2)

        search_frame = ttk.Frame(track_frame)
        search_frame.pack(fill='x', padx=2, pady=2)

        ttk.Label(search_frame, text="Suche:").pack(side='left')
        self.search_entry = ttk.Entry(search_frame, width=25)
        self.search_entry.pack(side='left', padx=5)
        self.search_entry.bind('<KeyRelease>', self.on_search)

        self.hide_dupes_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(search_frame, text="Duplikate ausblenden", variable=self.hide_dupes_var,
                        command=self.update_track_query).pack(side='left', padx=10)

        ttk.Button(search_frame, text="Markierte in Sidelist", command=self.add_selected_to_sidelist).pack(side='right',
                                                                                                           padx=2)
        ttk.Button(search_frame, text="Alle markieren", command=self.select_all_tracks).pack(side='right', padx=2)

        columns = ("artist", "album", "track_num", "title", "duration", "genre", "year", "bitrate", "filename",
                   "filepath", "preview")
        self.track_tree = ttk.Treeview(track_frame, columns=columns, show='headings', selectmode='extended')

        headers = ["Künstler", "Album", "Trk#", "Titel", "Länge", "Genre", "Jahr", "kbps", "Dateiname", "Pfad",
                   "Aktion"]
        widths = [120, 120, 40, 150, 50, 80, 50, 50, 120, 120, 60]

        for col, name, w in zip(columns, headers, widths):
            self.track_tree.heading(col, text=name)
            self.track_tree.column(col, width=w, anchor='w' if col not in ('track_num', 'duration', 'year', 'bitrate',
                                                                           'preview') else 'center')

        self.track_tree.column("filepath", width=0, stretch=False)
        self.make_tree_sortable(self.track_tree, columns)
        self.bind_preview(self.track_tree, '#11', 'filepath')

        track_scroll = ttk.Scrollbar(track_frame, orient="vertical", command=self.track_tree.yview)
        self.track_tree.configure(yscrollcommand=track_scroll.set)
        self.track_tree.pack(side='left', fill='both', expand=True)
        track_scroll.pack(side='right', fill='y')

        self.track_tree.bind('<Double-1>', self.on_tree_double_click)
        self.track_tree.bind('<Control-a>', self.select_all_tracks)

        sidelist_frame = ttk.LabelFrame(main_paned, text="Sidelist (Export)")
        main_paned.add(sidelist_frame, weight=1)

        side_cols = ("artist", "title", "filepath", "preview")
        self.sidelist = ttk.Treeview(sidelist_frame, columns=side_cols, show='headings', selectmode='extended')
        self.sidelist.heading("artist", text="Künstler")
        self.sidelist.heading("title", text="Titel")
        self.sidelist.heading("preview", text="Aktion")
        self.sidelist.column("artist", width=80)
        self.sidelist.column("title", width=120)
        self.sidelist.column("filepath", width=0, stretch=False)
        self.sidelist.column("preview", width=60, anchor='center')

        self.make_tree_sortable(self.sidelist, side_cols)
        self.bind_preview(self.sidelist, '#4', 'filepath')

        sidelist_scroll = ttk.Scrollbar(sidelist_frame, orient="vertical", command=self.sidelist.yview)
        self.sidelist.configure(yscrollcommand=sidelist_scroll.set)
        self.sidelist.pack(side='top', fill='both', expand=True)
        sidelist_scroll.pack(side='right', fill='y')
        self.sidelist.bind('<Double-1>', self.remove_from_sidelist)

        options_frame = ttk.Frame(sidelist_frame)
        options_frame.pack(fill='x', padx=5, pady=10)

        self.export_copy_var = tk.BooleanVar(value=True)
        self.export_playlist_var = tk.BooleanVar(value=True)

        ttk.Checkbutton(options_frame, text="In Zielordner kopieren", variable=self.export_copy_var).pack(anchor='w')
        ttk.Checkbutton(options_frame, text="Als Playliste (.m3u) exportieren", variable=self.export_playlist_var).pack(
            anchor='w')

        ttk.Button(sidelist_frame, text="Sidelist mit MP3val prüfen", command=self.check_sidelist_mp3val).pack(fill='x',
                                                                                                               pady=2)
        ttk.Button(sidelist_frame, text="Exportieren...", command=self.export_sidelist).pack(fill='x', pady=2)
        ttk.Button(sidelist_frame, text="Leeren",
                   command=lambda: self.sidelist.delete(*self.sidelist.get_children())).pack(fill='x', pady=2)

        self.load_left_list()
        self.load_tracks()

    def setup_settings_tab(self):
        folders_frame = ttk.LabelFrame(self.tab_settings, text="Musikbibliothek Ordner (Quelle)")
        folders_frame.pack(fill='x', padx=10, pady=5)

        self.lib_listbox = tk.Listbox(folders_frame, height=4)
        self.lib_listbox.pack(side='left', fill='x', expand=True, padx=5, pady=5)

        # Ordner aus der JSON laden
        for folder in self.settings.get("library_folders", []):
            self.lib_listbox.insert(tk.END, folder)

        btn_frame = ttk.Frame(folders_frame)
        btn_frame.pack(side='right', padx=5, pady=5)
        ttk.Button(btn_frame, text="Ordner hinzufügen", command=self.add_library_folder).pack(fill='x', pady=2)
        ttk.Button(btn_frame, text="Auswahl entfernen", command=self.remove_library_folder).pack(fill='x', pady=2)

        stick_frame = ttk.LabelFrame(self.tab_settings, text="Defekter Stick (Ziel)")
        stick_frame.pack(fill='x', padx=10, pady=5)

        # Stick-Pfad aus der JSON laden & überwachen (automatisch speichern bei Änderung)
        self.stick_path_var = tk.StringVar(value=self.settings.get("stick_path", r"M:\Stick_Backup"))
        self.stick_path_var.trace_add("write", self.save_settings)

        ttk.Entry(stick_frame, textvariable=self.stick_path_var).pack(side='left', fill='x', expand=True, padx=5,
                                                                      pady=5)
        ttk.Button(stick_frame, text="Durchsuchen", command=lambda: self.browse_folder(self.stick_path_var)).pack(
            side='right', padx=5, pady=5)

        mode_frame = ttk.LabelFrame(self.tab_settings, text="Recovery Modus")
        mode_frame.pack(fill='x', padx=10, pady=5)

        self.recovery_mode = tk.StringVar(value="copy")
        ttk.Radiobutton(mode_frame, text="Nur Playlist erstellen", variable=self.recovery_mode, value="playlist").pack(
            anchor='w', padx=10, pady=2)
        ttk.Radiobutton(mode_frame, text="Dateien auf Stick ersetzen & Playlist erstellen", variable=self.recovery_mode,
                        value="copy").pack(anchor='w', padx=10, pady=2)

        action_frame = ttk.LabelFrame(self.tab_settings, text="Aktionen & Log")
        action_frame.pack(fill='both', expand=True, padx=10, pady=5)

        ttk.Button(action_frame, text="1. Smarter Scan (Konsistenzprüfung & Indizierung)",
                   command=self.scan_library).pack(fill='x', padx=20, pady=5)
        ttk.Button(action_frame, text="2. Vorab-Check & Stick Recovery starten",
                   command=self.start_recovery_preview).pack(fill='x', padx=20, pady=5)
        ttk.Button(action_frame, text="3. Ziel-Stick mit MP3val prüfen", command=self.check_stick_mp3val).pack(fill='x',
                                                                                                               padx=20,
                                                                                                               pady=5)

        self.log_text = tk.Text(action_frame, height=10, state='disabled')
        self.log_text.pack(fill='both', expand=True, padx=20, pady=10)

    def normalize_text(self, text):
        if not text: return ""
        text = text.replace("´", "'").replace("`", "'").replace("’", "'").replace("‘", "'")
        return text.strip()

    def add_library_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.lib_listbox.insert(tk.END, folder)
            self.save_settings()  # Änderungen direkt in JSON speichern

    def remove_library_folder(self):
        selection = self.lib_listbox.curselection()
        if selection:
            self.lib_listbox.delete(selection[0])
            self.save_settings()  # Änderungen direkt in JSON speichern

    def browse_folder(self, string_var):
        folder = filedialog.askdirectory()
        if folder: string_var.set(folder)

    def log(self, message):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')
        self.root.update()

    def update_grouping_mode(self):
        mode = self.grouping_var.get()
        if mode == "artist_album":
            self.left_frame.config(text="Künstler")
            self.left_tree.heading("item", text="Alle Künstler")
            self.right_frame.config(text="Alben")
            self.right_tree.heading("item", text="Alle Alben")
        else:
            self.left_frame.config(text="Alben")
            self.left_tree.heading("item", text="Alle Alben")
            self.right_frame.config(text="Künstler")
            self.right_tree.heading("item", text="Alle Künstler")
        self.load_left_list()
        self.load_tracks()

    def load_left_list(self):
        for row in self.left_tree.get_children(): self.left_tree.delete(row)
        for row in self.right_tree.get_children(): self.right_tree.delete(row)

        mode = self.grouping_var.get()
        if mode == "artist_album":
            self.left_tree.insert("", "end", values=("(Alle Künstler)",))
            self.cursor.execute('SELECT DISTINCT artist FROM tracks WHERE artist != "" ORDER BY artist COLLATE NOCASE')
            self.right_tree.insert("", "end", values=("(Alle Alben)",))
        else:
            self.left_tree.insert("", "end", values=("(Alle Alben)",))
            self.cursor.execute('SELECT DISTINCT album FROM tracks WHERE album != "" ORDER BY album COLLATE NOCASE')
            self.right_tree.insert("", "end", values=("(Alle Künstler)",))

        for row in self.cursor.fetchall():
            self.left_tree.insert("", "end", values=(row[0],))

    def on_left_select(self, event):
        selection = self.left_tree.selection()
        if not selection: return
        left_val = self.left_tree.item(selection[0])['values'][0]
        mode = self.grouping_var.get()

        for row in self.right_tree.get_children(): self.right_tree.delete(row)

        if mode == "artist_album":
            self.right_tree.insert("", "end", values=("(Alle Alben)",))
            if left_val == "(Alle Künstler)":
                self.cursor.execute('SELECT DISTINCT album FROM tracks WHERE album != "" ORDER BY album COLLATE NOCASE')
            else:
                self.cursor.execute(
                    'SELECT DISTINCT album FROM tracks WHERE artist=? AND album != "" ORDER BY album COLLATE NOCASE',
                    (left_val,))
        else:
            self.right_tree.insert("", "end", values=("(Alle Künstler)",))
            if left_val == "(Alle Alben)":
                self.cursor.execute(
                    'SELECT DISTINCT artist FROM tracks WHERE artist != "" ORDER BY artist COLLATE NOCASE')
            else:
                self.cursor.execute(
                    'SELECT DISTINCT artist FROM tracks WHERE album=? AND artist != "" ORDER BY artist COLLATE NOCASE',
                    (left_val,))

        for row in self.cursor.fetchall():
            self.right_tree.insert("", "end", values=(row[0],))
        self.update_track_query()

    def on_right_select(self, event):
        self.update_track_query()

    def update_track_query(self):
        left_sel = self.left_tree.selection()
        right_sel = self.right_tree.selection()

        left_val = self.left_tree.item(left_sel[0])['values'][0] if left_sel else None
        right_val = self.right_tree.item(right_sel[0])['values'][0] if right_sel else None

        mode = self.grouping_var.get()
        artist, album = None, None

        if mode == "artist_album":
            if left_val and left_val != "(Alle Künstler)": artist = left_val
            if right_val and right_val != "(Alle Alben)": album = right_val
        else:
            if left_val and left_val != "(Alle Alben)": album = left_val
            if right_val and right_val != "(Alle Künstler)": artist = right_val

        self.load_tracks(artist=artist, album=album)

    def on_search(self, event):
        query = self.search_entry.get().strip()
        self.load_tracks(search_query=query)

    def load_tracks(self, artist=None, album=None, search_query=None):
        for row in self.track_tree.get_children(): self.track_tree.delete(row)

        query = 'SELECT artist, album, track_num, title, duration, genre, year, bitrate, filename, filepath FROM tracks WHERE 1=1'
        params = []

        if artist:
            query += ' AND artist=?'
            params.append(artist)
        if album:
            query += ' AND album=?'
            params.append(album)
        if search_query:
            query += ' AND (title LIKE ? OR filename LIKE ?)'
            params.extend([f'%{search_query}%', f'%{search_query}%'])

        if self.hide_dupes_var.get():
            query += ' GROUP BY artist, title'

        query += ' ORDER BY artist, album, track_num'

        self.cursor.execute(query, tuple(params))

        for row in self.cursor.fetchall():
            row = list(row)
            row[4] = format_length(row[4])
            if row[7]: row[7] = f"{int(row[7])}"
            row.append("[ ▶ ]")
            self.track_tree.insert("", "end", values=row)

    def select_all_tracks(self, event=None):
        self.track_tree.selection_add(self.track_tree.get_children())
        return "break"

    def add_selected_to_sidelist(self):
        selected = self.track_tree.selection()
        if not selected: return
        for item in selected:
            vals = self.track_tree.item(item, 'values')
            self.sidelist.insert("", "end", values=(vals[0], vals[3], vals[9], "[ ▶ ]"))

    def on_tree_double_click(self, event):
        region = self.track_tree.identify("region", event.x, event.y)
        if region == "cell" and self.track_tree.identify_column(event.x) != '#11':
            item = self.track_tree.identify_row(event.y)
            if item:
                vals = self.track_tree.item(item, 'values')
                self.sidelist.insert("", "end", values=(vals[0], vals[3], vals[9], "[ ▶ ]"))

    def remove_from_sidelist(self, event):
        for item in self.sidelist.selection(): self.sidelist.delete(item)

    # --- Scanner ---
    def scan_library(self):
        folders = self.lib_listbox.get(0, tk.END)
        if not folders:
            messagebox.showerror("Fehler", "Bitte mindestens einen Ordner hinzufügen!")
            return
        self.log("Lese bestehende Datenbankstruktur...")
        self.cursor.execute("SELECT filepath, filesize FROM tracks")
        existing_db = {row[0]: row[1] for row in self.cursor.fetchall()}

        found_files = set()
        new_count, updated_count = 0, 0

        self.log("Starte Delta-Scan der Ordner...")
        for folder_str in folders:
            lib_path = Path(folder_str)
            if not lib_path.exists(): continue
            for filepath in lib_path.rglob("*.mp3"):
                try:
                    filepath_str = str(filepath.resolve())
                    found_files.add(filepath_str)
                    current_size = filepath.stat().st_size
                    if filepath_str in existing_db and existing_db[filepath_str] == current_size:
                        continue
                    tag = TinyTag.get(filepath)
                    artist = str(tag.artist).strip() if tag.artist else "Unbekannt"
                    title = str(tag.title).strip() if tag.title else filepath.stem
                    album = str(tag.album).strip() if tag.album else ""
                    genre = str(tag.genre).strip() if tag.genre else ""
                    year = str(tag.year).strip()[:4] if tag.year else ""
                    track_num = str(tag.track).strip() if tag.track else ""

                    self.cursor.execute('''
                        INSERT OR REPLACE INTO tracks 
                        (filepath, filename, artist, title, album, genre, year, track_num, duration, filesize, bitrate, samplerate)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        filepath_str, filepath.name, artist, title, album, genre, year, track_num,
                        tag.duration, current_size, tag.bitrate, tag.samplerate
                    ))
                    if filepath_str in existing_db:
                        updated_count += 1
                    else:
                        new_count += 1
                    if (new_count + updated_count) % 50 == 0:
                        self.log(f"{new_count + updated_count} Dateien indiziert...")
                except:
                    pass
        missing_files = set(existing_db.keys()) - found_files
        for missing in missing_files:
            self.cursor.execute("DELETE FROM tracks WHERE filepath=?", (missing,))
        self.conn.commit()
        self.log(f"Scan fertig! Neu: {new_count}, Aktualisiert: {updated_count}, Gelöscht: {len(missing_files)}")
        self.load_left_list()
        self.load_tracks()

    def export_sidelist(self):
        items = self.sidelist.get_children()
        if not items: return
        do_copy, do_playlist = self.export_copy_var.get(), self.export_playlist_var.get()
        if not do_copy and not do_playlist:
            messagebox.showwarning("Warnung", "Bitte Export-Option auswählen.")
            return
        target_dir = filedialog.askdirectory(title="Zielordner auswählen")
        if not target_dir: return
        target_path = Path(target_dir)

        success_copy = 0
        playlist_entries = []
        for item in items:
            filepath = Path(self.sidelist.set(item, "filepath"))
            if do_copy:
                try:
                    shutil.copy2(filepath, target_path)
                    success_copy += 1
                    if do_playlist: playlist_entries.append(filepath.name)
                except Exception as e:
                    print(f"Fehler: {e}")
            else:
                if do_playlist: playlist_entries.append(str(filepath.resolve()))
        if do_playlist:
            try:
                with open(target_path / "Sidelist_Export.m3u", "w", encoding="utf-8") as f:
                    f.write("#EXTM3U\n" + "\n".join(playlist_entries) + "\n")
            except:
                pass
        msg = "Export erfolgreich!\n\n"
        if do_copy: msg += f"Kopiert: {success_copy}\n"
        if do_playlist: msg += "Playliste erstellt.\n"
        messagebox.showinfo("Export Status", msg)

    def start_recovery_preview(self):
        stick_path = Path(self.stick_path_var.get())
        if not stick_path.exists():
            messagebox.showerror("Fehler", "Zielpfad (Stick) existiert nicht!")
            return

        mode = self.recovery_mode.get()
        playlist_path = stick_path / "recovered_playlist.m3u"
        self.log(f"Analysiere Dateien auf dem Stick...")

        proposed_matches = []
        missing_list = []

        for corrupted_file in stick_path.rglob("*.mp3"):
            match_found = False
            source_filepath = None

            try:
                tag = TinyTag.get(corrupted_file)
                c_artist = self.normalize_text(str(tag.artist)) if tag.artist else ""
                c_title = self.normalize_text(str(tag.title)) if tag.title else ""
            except:
                c_artist, c_title = "", ""

            if c_artist and c_title:
                self.cursor.execute('SELECT filepath FROM tracks WHERE artist=? AND title=? LIMIT 1',
                                    (c_artist, c_title))
                result = self.cursor.fetchone()
                if result: source_filepath, match_found = result[0], True

            if not match_found:
                self.cursor.execute('SELECT filepath FROM tracks WHERE filename=? LIMIT 1', (corrupted_file.name,))
                result = self.cursor.fetchone()
                if result: source_filepath, match_found = result[0], True

            if not match_found and c_artist and c_title:
                self.cursor.execute('SELECT filepath FROM tracks WHERE artist LIKE ? AND title LIKE ? LIMIT 1',
                                    (f'%{c_artist}%', f'%{c_title}%'))
                result = self.cursor.fetchone()
                if result: source_filepath, match_found = result[0], True

            if not match_found:
                self.cursor.execute('SELECT filepath FROM tracks WHERE filename LIKE ? LIMIT 1',
                                    (f'%{corrupted_file.stem}%',))
                result = self.cursor.fetchone()
                if result: source_filepath, match_found = result[0], True

            if not match_found and "-" in corrupted_file.stem:
                parts = [p.strip() for p in corrupted_file.stem.split("-")]
                longest_part = max(parts, key=len)
                if len(longest_part) > 5:
                    self.cursor.execute('SELECT filepath FROM tracks WHERE filename LIKE ? LIMIT 1',
                                        (f'%{longest_part}%',))
                    result = self.cursor.fetchone()
                    if result: source_filepath, match_found = result[0], True

            if match_found and source_filepath:
                proposed_matches.append((corrupted_file.name, str(corrupted_file.resolve()), source_filepath))
            else:
                missing_list.append((corrupted_file.name, str(corrupted_file.resolve())))

        self.log(
            f"Analyse fertig. {len(proposed_matches)} automatische Treffer, {len(missing_list)} fehlen. Öffne Manager...")
        self.show_recovery_manager(proposed_matches, missing_list, playlist_path, mode)

    def show_recovery_manager(self, proposed_matches, missing_list, playlist_path, mode):
        popup = tk.Toplevel(self.root)
        popup.title("Recovery Manager - Überprüfung & Reparatur")
        popup.geometry("1200x750")

        paned = ttk.PanedWindow(popup, orient=tk.VERTICAL)
        paned.pack(fill='both', expand=True, padx=10, pady=10)

        match_frame = ttk.LabelFrame(paned, text="Bereit zur Reparatur (Klicke auf ☑ um Ausnahmen zu definieren)")
        paned.add(match_frame, weight=3)

        toolbar = ttk.Frame(match_frame)
        toolbar.pack(fill='x', padx=5, pady=5)

        def toggle_all(state="\u2611"):
            for item in match_tree.get_children(): match_tree.set(item, "check", state)

        ttk.Button(toolbar, text="Alle anwählen (☑)", command=lambda: toggle_all("\u2611")).pack(side='left', padx=2)
        ttk.Button(toolbar, text="Alle abwählen (☐)", command=lambda: toggle_all("\u2610")).pack(side='left', padx=2)

        match_cols = ("check", "filename", "src_path", "status", "corr_path_hidden", "preview")
        match_tree = ttk.Treeview(match_frame, columns=match_cols, show='headings', selectmode='extended')
        match_tree.heading("check", text="Status")
        match_tree.heading("filename", text="Dateiname (auf Stick)")
        match_tree.heading("src_path", text="Quelle (Bibliothek)")
        match_tree.heading("status", text="Info")
        match_tree.heading("preview", text="Aktion")

        match_tree.column("check", width=50, anchor='center')
        match_tree.column("filename", width=300)
        match_tree.column("src_path", width=400)
        match_tree.column("status", width=120)
        match_tree.column("corr_path_hidden", width=0, stretch=False)
        match_tree.column("preview", width=60, anchor='center')

        self.make_tree_sortable(match_tree, match_cols)
        self.bind_preview(match_tree, '#6', 'src_path')

        mt_scroll = ttk.Scrollbar(match_frame, orient="vertical", command=match_tree.yview)
        match_tree.configure(yscrollcommand=mt_scroll.set)
        match_tree.pack(side='left', fill='both', expand=True, padx=5, pady=5)
        mt_scroll.pack(side='right', fill='y')

        def on_check_click(event):
            region = match_tree.identify("region", event.x, event.y)
            if region == "cell" and match_tree.identify_column(event.x) == '#1':
                item = match_tree.identify_row(event.y)
                if item:
                    current = match_tree.set(item, "check")
                    if current in ["\u2611", "\u2610"]:
                        match_tree.set(item, "check", "\u2610" if current == "\u2611" else "\u2611")

        match_tree.bind('<ButtonRelease-1>', on_check_click, add='+')

        for m_name, m_corr_path, m_src_path in proposed_matches:
            match_tree.insert("", "end", values=("\u2611", m_name, m_src_path, "Auto-Treffer", m_corr_path, "[ ▶ ]"))

        missing_frame = ttk.LabelFrame(paned,
                                       text=f"Fehlende Dateien ({len(missing_list)}) - Zum manuellen Suchen markieren")
        paned.add(missing_frame, weight=2)

        missing_cols = ("filename", "filepath", "preview")
        missing_tree = ttk.Treeview(missing_frame, columns=missing_cols, show='headings')
        missing_tree.heading("filename", text="Dateiname (auf Stick)")
        missing_tree.heading("filepath", text="Absoluter Pfad")
        missing_tree.heading("preview", text="Aktion")

        missing_tree.column("filename", width=300)
        missing_tree.column("filepath", width=400)
        missing_tree.column("preview", width=60, anchor='center')

        self.make_tree_sortable(missing_tree, missing_cols)
        self.bind_preview(missing_tree, '#3', 'filepath')

        ms_scroll = ttk.Scrollbar(missing_frame, orient="vertical", command=missing_tree.yview)
        missing_tree.configure(yscrollcommand=ms_scroll.set)
        missing_tree.pack(side='top', fill='both', expand=True, padx=5, pady=5)
        ms_scroll.pack(side='right', fill='y')

        for m_name, m_path in missing_list:
            missing_tree.insert("", "end", values=(m_name, m_path, "[ ▶ ]"))

        btn_search = ttk.Button(missing_frame, text="Manuelle Suche für markierte Datei",
                                command=lambda: self.open_manual_search_dialog(popup, missing_tree, match_tree,
                                                                               missing_frame))
        btn_search.pack(pady=5)

        def execute_repair():
            items = match_tree.get_children()
            count_repaired = 0

            with open(playlist_path, "w", encoding="utf-8") as m3u:
                m3u.write("#EXTM3U\n")

                for item in items:
                    if match_tree.set(item, "check") == "\u2611":
                        corr_path = Path(match_tree.set(item, "corr_path_hidden"))
                        src_path = Path(match_tree.set(item, "src_path"))

                        try:
                            if mode == "copy":
                                shutil.copy2(src_path, corr_path)
                                m3u.write(f"{corr_path.resolve()}\n")
                            else:
                                m3u.write(f"{src_path.resolve()}\n")

                            match_tree.set(item, "status", "Erfolgreich!")
                            match_tree.set(item, "check", "---")
                            count_repaired += 1
                        except Exception as e:
                            match_tree.set(item, "status", "Fehler beim Kopieren")

            messagebox.showinfo("Fertig",
                                f"Der Vorgang wurde abgeschlossen.\nEs wurden {count_repaired} Dateien verarbeitet.")
            self.log(f"Finale Reparatur abgeschlossen: {count_repaired} angewendet.")

        action_frame = ttk.Frame(popup)
        action_frame.pack(fill='x', padx=10, pady=10)
        btn_execute = ttk.Button(action_frame, text="Reparatur für abgehakte Dateien JETZT ausführen",
                                 command=execute_repair)
        btn_execute.pack(fill='x', ipady=5)

    def open_manual_search_dialog(self, parent_popup, missing_tree, match_tree, missing_frame_ref):
        selected = missing_tree.selection()
        if not selected:
            messagebox.showinfo("Info", "Bitte zuerst eine Datei aus der unteren Liste auswählen.")
            return

        item = selected[0]
        corrupted_filename, corrupted_filepath, _ = missing_tree.item(item, 'values')

        search_popup = tk.Toplevel(parent_popup)
        search_popup.title(f"Suche Ersatz für: {corrupted_filename}")
        search_popup.geometry("900x450")

        top_frame = ttk.Frame(search_popup)
        top_frame.pack(fill='x', padx=10, pady=10)

        ttk.Label(top_frame, text="Suchen nach:").pack(side='left', padx=5)
        s_entry = ttk.Entry(top_frame, width=40)
        s_entry.pack(side='left', padx=5)

        clean_name = Path(corrupted_filename).stem
        s_entry.insert(0, clean_name)

        res_cols = ("artist", "title", "kbps", "filename", "filepath", "preview")
        result_tree = ttk.Treeview(search_popup, columns=res_cols, show='headings')
        result_tree.heading("artist", text="Künstler")
        result_tree.heading("title", text="Titel")
        result_tree.heading("kbps", text="kbps")
        result_tree.heading("filename", text="Dateiname")
        result_tree.heading("filepath", text="Pfad")
        result_tree.heading("preview", text="Aktion")

        result_tree.column("artist", width=120)
        result_tree.column("title", width=150)
        result_tree.column("kbps", width=50, anchor='center')
        result_tree.column("filename", width=150)
        result_tree.column("filepath", width=150)
        result_tree.column("preview", width=60, anchor='center')

        self.make_tree_sortable(result_tree, res_cols)
        self.bind_preview(result_tree, '#6', 'filepath')

        def execute_manual_query(event=None):
            for row in result_tree.get_children(): result_tree.delete(row)
            q = s_entry.get().strip()
            self.cursor.execute('''
                                SELECT artist, title, bitrate, filename, filepath
                                FROM tracks
                                WHERE filename LIKE ?
                                   OR artist LIKE ?
                                   OR title LIKE ?
                                ''', (f'%{q}%', f'%{q}%', f'%{q}%'))
            for row in self.cursor.fetchall():
                r = list(row)
                if r[2]: r[2] = f"{int(r[2])}"
                r.append("[ ▶ ]")
                result_tree.insert("", "end", values=r)

        execute_manual_query()
        s_entry.bind('<Return>', execute_manual_query)
        ttk.Button(top_frame, text="Suchen", command=execute_manual_query).pack(side='left', padx=5)

        res_scroll = ttk.Scrollbar(search_popup, orient="vertical", command=result_tree.yview)
        result_tree.configure(yscrollcommand=res_scroll.set)
        result_tree.pack(fill='both', expand=True, padx=10, pady=5)
        res_scroll.pack(side='right', fill='y')

        def apply_manual_match():
            sel_res = result_tree.selection()
            if not sel_res: return

            source_filepath = result_tree.item(sel_res[0], 'values')[4]
            missing_tree.delete(item)
            match_tree.insert("", "end", values=("\u2611", corrupted_filename, source_filepath, "Manuell verknüpft",
                                                 corrupted_filepath, "[ ▶ ]"))
            missing_frame_ref.config(
                text=f"Fehlende Dateien ({len(missing_tree.get_children())}) - Zum manuellen Suchen markieren")
            search_popup.destroy()

        ttk.Button(search_popup, text="Markierten Titel als Ersatz anwenden", command=apply_manual_match).pack(pady=10)

    # --- ÜBERARBEITET: MP3val Fehlerbehebung (UTF-8 Bug fix) ---
    def check_sidelist_mp3val(self):
        items = self.sidelist.get_children()
        if not items:
            messagebox.showinfo("Info", "Die Sidelist ist leer.")
            return
        file_paths = [self.sidelist.set(item, "filepath") for item in items]
        self.run_mp3val_check(file_paths, "Sidelist")

    def check_stick_mp3val(self):
        stick_path = Path(self.stick_path_var.get())
        if not stick_path.exists():
            messagebox.showerror("Fehler", "Zielpfad existiert nicht!")
            return
        self.log("Sammle MP3s auf dem Ziel-Stick für MP3val...")
        file_paths = [str(f.resolve()) for f in stick_path.rglob("*.mp3")]
        if not file_paths:
            messagebox.showinfo("Info", "Keine MP3-Dateien auf dem Ziel-Stick gefunden.")
            return
        self.run_mp3val_check(file_paths, f"Ziel-Stick ({len(file_paths)} Dateien)")

    def run_mp3val_check(self, file_paths, context_name):
        if not self.mp3val_path.exists():
            messagebox.showerror("Fehler", f"mp3val.exe wurde nicht gefunden unter:\n{self.mp3val_path.resolve()}")
            return

        popup = tk.Toplevel(self.root)
        popup.title(f"MP3val Überprüfung: {context_name}")
        popup.geometry("900x500")

        ttk.Label(popup, text="Überprüfe Dateien auf MPEG-Stream-Fehler und beschädigte Header...").pack(pady=10)

        cols = ("file", "status", "details", "filepath", "preview")
        tree = ttk.Treeview(popup, columns=cols, show='headings')
        tree.heading("file", text="Datei")
        tree.heading("status", text="Status")
        tree.heading("details", text="Details")
        tree.heading("preview", text="Aktion")

        tree.column("file", width=400)
        tree.column("status", width=80, anchor='center')
        tree.column("details", width=300)
        tree.column("filepath", width=0, stretch=False)
        tree.column("preview", width=60, anchor='center')

        self.make_tree_sortable(tree, cols)
        self.bind_preview(tree, '#5', 'filepath')

        scroll = ttk.Scrollbar(popup, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(fill='both', expand=True, padx=10, pady=5)
        scroll.pack(side='right', fill='y')

        popup.update()
        corrupted_files = []

        for path in file_paths:
            try:
                # WICHTIG: capture_output ohne text=True, um Raw-Bytes zu empfangen
                result = subprocess.run([str(self.mp3val_path), path], capture_output=True, check=False)

                # Tolerantes decodieren, um den UTF-8 Absturz bei Sonderzeichen zu umgehen
                output = result.stdout.decode('cp1252', errors='replace')

                if "WARNING:" in output:
                    warning_detail = output.split("WARNING:")[-1].strip()
                    tree.insert("", "end", values=(Path(path).name, "FEHLER", warning_detail, path, "[ ▶ ]"))
                    corrupted_files.append(path)
                elif "ERROR:" in output:
                    error_detail = output.split("ERROR:")[-1].strip()
                    tree.insert("", "end", values=(Path(path).name, "KRITISCH", error_detail, path, "[ ▶ ]"))
                    corrupted_files.append(path)
                else:
                    tree.insert("", "end", values=(Path(path).name, "OK", "Keine Fehler gefunden", path, "[ ▶ ]"))
            except Exception as e:
                tree.insert("", "end", values=(Path(path).name, "SYSTEM-FEHLER", str(e), path, "[ ▶ ]"))

        def fix_corrupted_files():
            if not corrupted_files: return
            success = 0
            for path in corrupted_files:
                try:
                    subprocess.run([str(self.mp3val_path), "-f", "-nb", "-t", path], capture_output=True, check=False)
                    success += 1
                except Exception as e:
                    print(f"Fehler: {e}")
            messagebox.showinfo("Reparatur abgeschlossen", f"{success} von {len(corrupted_files)} Dateien repariert.")
            popup.destroy()

        btn_frame = ttk.Frame(popup)
        btn_frame.pack(fill='x', padx=10, pady=10)
        btn_fix = ttk.Button(btn_frame, text=f"Defekte Dateien reparieren ({len(corrupted_files)} gefunden)",
                             command=fix_corrupted_files)
        btn_fix.pack(side='right', padx=5)
        if not corrupted_files: btn_fix.state(['disabled'])


if __name__ == "__main__":
    root = tk.Tk()
    app = DJRecoveryApp(root)
    root.mainloop()