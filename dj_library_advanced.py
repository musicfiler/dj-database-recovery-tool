import sqlite3
import os
import shutil
import subprocess
import json
import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES

    DND_SUPPORTED = True
except ImportError:
    DND_SUPPORTED = False

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
        self.root.title("DJ Database Tool - Dual Library, MP3val & Drag'n'Drop")
        self.root.geometry("1400x850")

        if getattr(sys, 'frozen', False):
            base_path = Path(sys._MEIPASS)
        else:
            base_path = Path(__file__).parent

        self.mp3val_path = base_path / "mp3val" / "mp3val.exe"
        self.mp3val_available = self.mp3val_path.exists()

        self.settings = {
            "library_folders_A": [],
            "library_folders_B": [],
            "stick_path": r"M:\Stick_Backup"
        }
        self.load_settings()

        self.views = {}
        self.setup_styles()
        self.init_db()
        self.create_gui()

    def setup_styles(self):
        style = ttk.Style()
        style.configure("Huge.Vertical.TScrollbar", width=35, arrowsize=35)

    def init_db(self):
        self.conn = sqlite3.connect(DB_FILE)
        self.cursor = self.conn.cursor()

        try:
            self.cursor.execute("SELECT library_id FROM tracks LIMIT 1")
        except sqlite3.OperationalError:
            self.cursor.execute('DROP TABLE IF EXISTS tracks')

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
                                INTEGER,
                                library_id
                                TEXT
                            )
                            ''')

        # MASSIVE BESCHLEUNIGUNG: Indizes für den Inkonsistenz-Filter anlegen
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_lib_artist_title ON tracks(library_id, artist, title)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_lib_filename ON tracks(library_id, filename)')

        self.conn.commit()

    def load_settings(self):
        if Path(SETTINGS_FILE).exists():
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    loaded_data = json.load(f)
                    self.settings.update(loaded_data)
            except Exception as e:
                print(f"Fehler beim Laden der Einstellungen: {e}")

    def save_settings(self, *args):
        if hasattr(self, 'lib_listbox_a') and hasattr(self, 'lib_listbox_b') and hasattr(self, 'stick_path_var'):
            self.settings["library_folders_A"] = list(self.lib_listbox_a.get(0, tk.END))
            self.settings["library_folders_B"] = list(self.lib_listbox_b.get(0, tk.END))
            self.settings["stick_path"] = self.stick_path_var.get()
            try:
                with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                    json.dump(self.settings, f, indent=4)
            except Exception as e:
                print(f"Fehler beim Speichern: {e}")

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
            if col not in ["folder_btn", "preview_btn", "check"]:
                tree.heading(col, command=lambda c=col, tv=tree: self.sort_column(tv, c, False))

    def bind_actions(self, tree, folder_col, preview_col, path_col_name):
        def on_click(event):
            region = tree.identify("region", event.x, event.y)
            if region == "cell":
                col = tree.identify_column(event.x)
                if col in [folder_col, preview_col]:
                    item = tree.identify_row(event.y)
                    if item:
                        filepath = tree.set(item, path_col_name)
                        if col == folder_col:
                            try:
                                if Path(filepath).exists():
                                    os.startfile(Path(filepath).parent)
                            except:
                                pass
                        elif col == preview_col:
                            try:
                                if Path(filepath).exists():
                                    os.startfile(filepath)
                            except:
                                pass

        tree.bind('<ButtonRelease-1>', on_click, add='+')

        if DND_SUPPORTED:
            tree.drag_source_register(1, DND_FILES)
            tree.dnd_bind('<<DragInitCmd>>',
                          lambda event, tv=tree, pcol=path_col_name: self.on_drag_init(event, tv, pcol))

    def on_drag_init(self, event, tree, path_col_name):
        sel = tree.selection()
        if not sel: return None
        paths = []
        for item in sel:
            path = tree.set(item, path_col_name)
            paths.append(str(Path(path).resolve()))
        return ('copy', DND_FILES, tuple(paths))

    def create_gui(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True, padx=5, pady=5)

        tab_lib_a = ttk.Frame(notebook)
        notebook.add(tab_lib_a, text='Musikbibliothek A')
        self.setup_library_tab(tab_lib_a, 'A')

        tab_lib_b = ttk.Frame(notebook)
        notebook.add(tab_lib_b, text='Musikbibliothek B')
        self.setup_library_tab(tab_lib_b, 'B')

        tab_settings = ttk.Frame(notebook)
        notebook.add(tab_settings, text='Einstellungen & Recovery')
        self.setup_settings_tab(tab_settings)

    def setup_library_tab(self, parent_frame, lib_id):
        self.views[lib_id] = {}
        v = self.views[lib_id]

        view_frame = ttk.Frame(parent_frame)
        view_frame.pack(fill='x', padx=5, pady=5)

        ttk.Label(view_frame, text="Ansicht / Gruppierung:").pack(side='left', padx=5)
        v['grouping_var'] = tk.StringVar(value="artist_album")
        ttk.Radiobutton(view_frame, text="Künstler -> Alben", variable=v['grouping_var'], value="artist_album",
                        command=lambda lid=lib_id: self.update_grouping_mode(lid)).pack(side='left', padx=10)
        ttk.Radiobutton(view_frame, text="Alben -> Künstler", variable=v['grouping_var'], value="album_artist",
                        command=lambda lid=lib_id: self.update_grouping_mode(lid)).pack(side='left', padx=10)

        main_paned = ttk.PanedWindow(parent_frame, orient=tk.HORIZONTAL)
        main_paned.pack(fill='both', expand=True, padx=5, pady=5)

        winamp_paned = ttk.PanedWindow(main_paned, orient=tk.VERTICAL)
        main_paned.add(winamp_paned, weight=4)

        top_split = ttk.PanedWindow(winamp_paned, orient=tk.HORIZONTAL)
        winamp_paned.add(top_split, weight=1)

        v['left_frame'] = ttk.LabelFrame(top_split, text="Künstler")
        top_split.add(v['left_frame'], weight=1)
        v['left_tree'] = ttk.Treeview(v['left_frame'], columns=("item",), show='headings', selectmode='browse')
        v['left_tree'].heading("item", text="Alle Künstler")
        self.make_tree_sortable(v['left_tree'], ("item",))
        left_scroll = ttk.Scrollbar(v['left_frame'], orient="vertical", command=v['left_tree'].yview)
        v['left_tree'].configure(yscrollcommand=left_scroll.set)
        v['left_tree'].pack(side='left', fill='both', expand=True)
        left_scroll.pack(side='right', fill='y')
        v['left_tree'].bind('<<TreeviewSelect>>', lambda event, lid=lib_id: self.on_left_select(event, lid))

        v['right_frame'] = ttk.LabelFrame(top_split, text="Alben")
        top_split.add(v['right_frame'], weight=1)
        v['right_tree'] = ttk.Treeview(v['right_frame'], columns=("item",), show='headings', selectmode='browse')
        v['right_tree'].heading("item", text="Alle Alben")
        self.make_tree_sortable(v['right_tree'], ("item",))
        right_scroll = ttk.Scrollbar(v['right_frame'], orient="vertical", command=v['right_tree'].yview)
        v['right_tree'].configure(yscrollcommand=right_scroll.set)
        v['right_tree'].pack(side='left', fill='both', expand=True)
        right_scroll.pack(side='right', fill='y')
        v['right_tree'].bind('<<TreeviewSelect>>', lambda event, lid=lib_id: self.on_right_select(event, lid))

        track_frame = ttk.LabelFrame(winamp_paned, text="Tracks (Mit der Maus markieren & rausziehen)")
        winamp_paned.add(track_frame, weight=2)

        search_frame = ttk.Frame(track_frame)
        search_frame.pack(fill='x', padx=2, pady=2)

        ttk.Label(search_frame, text="Suche:").pack(side='left')
        v['search_entry'] = ttk.Entry(search_frame, width=25)
        v['search_entry'].pack(side='left', padx=5)
        v['search_entry'].bind('<KeyRelease>', lambda event, lid=lib_id: self.on_search(event, lid))

        v['hide_dupes_var'] = tk.BooleanVar(value=False)
        ttk.Checkbutton(search_frame, text="Duplikate ausblenden", variable=v['hide_dupes_var'],
                        command=lambda lid=lib_id: self.update_track_query(lid)).pack(side='left', padx=5)

        other_lib = 'B' if lib_id == 'A' else 'A'
        v['missing_in_other_var'] = tk.BooleanVar(value=False)
        ttk.Checkbutton(search_frame, text=f"Zeige nur Tracks, die in Bibliothek {other_lib} fehlen",
                        variable=v['missing_in_other_var'],
                        command=lambda lid=lib_id: self.update_track_query(lid)).pack(side='left', padx=5)

        ttk.Button(search_frame, text="Markierte in Sidelist",
                   command=lambda lid=lib_id: self.add_selected_to_sidelist(lid)).pack(side='right', padx=2)
        ttk.Button(search_frame, text="Alle markieren", command=lambda lid=lib_id: self.select_all_tracks(lid)).pack(
            side='right', padx=2)
        ttk.Button(search_frame, text="Inkonsistenz-Report exportieren",
                   command=lambda lid=lib_id: self.export_missing_report(lid)).pack(side='right', padx=2)

        columns = ("artist", "album", "track_num", "title", "duration", "genre", "year", "bitrate", "filename",
                   "filepath", "folder_btn", "preview_btn")
        v['track_tree'] = ttk.Treeview(track_frame, columns=columns, show='headings', selectmode='extended')

        headers = ["Künstler", "Album", "Trk#", "Titel", "Länge", "Genre", "Jahr", "kbps", "Dateiname", "Pfad", "Ort",
                   "Play"]
        widths = [120, 120, 40, 150, 50, 80, 50, 50, 120, 120, 40, 40]

        for col, name, w in zip(columns, headers, widths):
            v['track_tree'].heading(col, text=name)
            v['track_tree'].column(col, width=w,
                                   anchor='w' if col not in ('track_num', 'duration', 'year', 'bitrate', 'folder_btn',
                                                             'preview_btn') else 'center')

        v['track_tree'].column("filepath", width=0, stretch=False)
        self.make_tree_sortable(v['track_tree'], columns)

        self.bind_actions(v['track_tree'], '#11', '#12', 'filepath')

        track_scroll = ttk.Scrollbar(track_frame, orient="vertical", command=v['track_tree'].yview)
        v['track_tree'].configure(yscrollcommand=track_scroll.set)
        v['track_tree'].pack(side='left', fill='both', expand=True)
        track_scroll.pack(side='right', fill='y')

        v['track_tree'].bind('<Double-1>', lambda event, lid=lib_id: self.on_tree_double_click(event, lid))
        v['track_tree'].bind('<Control-a>', lambda event, lid=lib_id: self.select_all_tracks(lid))

        sidelist_frame = ttk.LabelFrame(main_paned, text="Sidelist (Export & Drag Out)")
        main_paned.add(sidelist_frame, weight=1)

        side_cols = ("artist", "title", "filepath", "folder_btn", "preview_btn")
        v['sidelist'] = ttk.Treeview(sidelist_frame, columns=side_cols, show='headings', selectmode='extended')
        v['sidelist'].heading("artist", text="Künstler")
        v['sidelist'].heading("title", text="Titel")
        v['sidelist'].heading("folder_btn", text="Ort")
        v['sidelist'].heading("preview_btn", text="Play")

        v['sidelist'].column("artist", width=80)
        v['sidelist'].column("title", width=120)
        v['sidelist'].column("filepath", width=0, stretch=False)
        v['sidelist'].column("folder_btn", width=40, anchor='center')
        v['sidelist'].column("preview_btn", width=40, anchor='center')

        self.make_tree_sortable(v['sidelist'], side_cols)
        self.bind_actions(v['sidelist'], '#4', '#5', 'filepath')

        sidelist_scroll = ttk.Scrollbar(sidelist_frame, orient="vertical", command=v['sidelist'].yview)
        v['sidelist'].configure(yscrollcommand=sidelist_scroll.set)
        v['sidelist'].pack(side='top', fill='both', expand=True)
        sidelist_scroll.pack(side='right', fill='y')
        v['sidelist'].bind('<Double-1>', lambda event, lid=lib_id: self.remove_from_sidelist(event, lid))

        options_frame = ttk.Frame(sidelist_frame)
        options_frame.pack(fill='x', padx=5, pady=10)

        v['export_copy_var'] = tk.BooleanVar(value=True)
        v['export_playlist_var'] = tk.BooleanVar(value=True)

        ttk.Checkbutton(options_frame, text="In Zielordner kopieren", variable=v['export_copy_var']).pack(anchor='w')
        ttk.Checkbutton(options_frame, text="Als Playliste (.m3u) exportieren", variable=v['export_playlist_var']).pack(
            anchor='w')

        # Deaktivieren falls MP3val fehlt
        btn_state = tk.NORMAL if self.mp3val_available else tk.DISABLED
        ttk.Button(sidelist_frame, text="Sidelist mit MP3val prüfen", state=btn_state,
                   command=lambda lid=lib_id: self.check_sidelist_mp3val(lid)).pack(fill='x', pady=2)
        ttk.Button(sidelist_frame, text="Exportieren...", command=lambda lid=lib_id: self.export_sidelist(lid)).pack(
            fill='x', pady=2)
        ttk.Button(sidelist_frame, text="Leeren",
                   command=lambda lid=lib_id: v['sidelist'].delete(*v['sidelist'].get_children())).pack(fill='x',
                                                                                                        pady=2)

        self.load_left_list(lib_id)
        self.load_tracks(lib_id)

    def setup_settings_tab(self, parent_frame):
        paned = ttk.PanedWindow(parent_frame, orient=tk.HORIZONTAL)
        paned.pack(fill='both', expand=True, padx=5, pady=5)

        left_col = ttk.Frame(paned)
        paned.add(left_col, weight=1)

        folders_frame_a = ttk.LabelFrame(left_col, text="Musikbibliothek A Ordner (Master)")
        folders_frame_a.pack(fill='x', padx=10, pady=5)
        self.lib_listbox_a = tk.Listbox(folders_frame_a, height=3)
        self.lib_listbox_a.pack(side='left', fill='x', expand=True, padx=5, pady=5)
        for folder in self.settings.get("library_folders_A", []): self.lib_listbox_a.insert(tk.END, folder)
        btn_frame_a = ttk.Frame(folders_frame_a)
        btn_frame_a.pack(side='right', padx=5, pady=5)
        ttk.Button(btn_frame_a, text="Hinzufügen", command=lambda: self.add_library_folder(self.lib_listbox_a)).pack(
            fill='x', pady=2)
        ttk.Button(btn_frame_a, text="Entfernen", command=lambda: self.remove_library_folder(self.lib_listbox_a)).pack(
            fill='x', pady=2)

        folders_frame_b = ttk.LabelFrame(left_col, text="Musikbibliothek B Ordner (Vergleich)")
        folders_frame_b.pack(fill='x', padx=10, pady=5)
        self.lib_listbox_b = tk.Listbox(folders_frame_b, height=3)
        self.lib_listbox_b.pack(side='left', fill='x', expand=True, padx=5, pady=5)
        for folder in self.settings.get("library_folders_B", []): self.lib_listbox_b.insert(tk.END, folder)
        btn_frame_b = ttk.Frame(folders_frame_b)
        btn_frame_b.pack(side='right', padx=5, pady=5)
        ttk.Button(btn_frame_b, text="Hinzufügen", command=lambda: self.add_library_folder(self.lib_listbox_b)).pack(
            fill='x', pady=2)
        ttk.Button(btn_frame_b, text="Entfernen", command=lambda: self.remove_library_folder(self.lib_listbox_b)).pack(
            fill='x', pady=2)

        db_maint_frame = ttk.LabelFrame(left_col, text="Datenbank Wartung")
        db_maint_frame.pack(fill='x', padx=10, pady=5)
        ttk.Button(db_maint_frame, text="Datenbank leeren", command=self.clear_database).pack(side='left', fill='x',
                                                                                              expand=True, padx=5,
                                                                                              pady=5)
        ttk.Button(db_maint_frame, text="Datenbank sichern", command=self.backup_database).pack(side='left', fill='x',
                                                                                                expand=True, padx=5,
                                                                                                pady=5)
        ttk.Button(db_maint_frame, text="Wiederherstellen", command=self.restore_database).pack(side='left', fill='x',
                                                                                                expand=True, padx=5,
                                                                                                pady=5)

        right_col = ttk.Frame(paned)
        paned.add(right_col, weight=1)

        stick_frame = ttk.LabelFrame(right_col, text="Defekter Stick (Ziel)")
        stick_frame.pack(fill='x', padx=10, pady=5)
        self.stick_path_var = tk.StringVar(value=self.settings.get("stick_path", r"M:\Stick_Backup"))
        self.stick_path_var.trace_add("write", self.save_settings)
        ttk.Entry(stick_frame, textvariable=self.stick_path_var).pack(side='left', fill='x', expand=True, padx=5,
                                                                      pady=5)
        ttk.Button(stick_frame, text="Durchsuchen", command=lambda: self.browse_folder(self.stick_path_var)).pack(
            side='right', padx=5, pady=5)

        mode_frame = ttk.LabelFrame(right_col, text="Recovery Modus (nutzt Bibliothek A als Referenz)")
        mode_frame.pack(fill='x', padx=10, pady=5)
        self.recovery_mode = tk.StringVar(value="copy")
        ttk.Radiobutton(mode_frame, text="Nur Playlist erstellen", variable=self.recovery_mode, value="playlist").pack(
            anchor='w', padx=10, pady=2)
        ttk.Radiobutton(mode_frame, text="Dateien auf Stick ersetzen & Playlist erstellen", variable=self.recovery_mode,
                        value="copy").pack(anchor='w', padx=10, pady=2)

        action_frame = ttk.LabelFrame(right_col, text="Aktionen & Log")
        action_frame.pack(fill='both', expand=True, padx=10, pady=5)

        ttk.Button(action_frame, text="1. Smarter Scan (Beide Bibliotheken indizieren)",
                   command=self.scan_libraries).pack(fill='x', padx=20, pady=5)
        ttk.Button(action_frame, text="2. Vorab-Check & Stick Recovery starten",
                   command=self.start_recovery_preview).pack(fill='x', padx=20, pady=5)

        btn_state = tk.NORMAL if self.mp3val_available else tk.DISABLED
        ttk.Button(action_frame, text="3. Ziel-Stick mit MP3val prüfen", state=btn_state,
                   command=self.check_stick_mp3val).pack(fill='x', padx=20, pady=5)

        self.log_text = tk.Text(action_frame, height=10, state='disabled')
        self.log_text.pack(fill='both', expand=True, padx=20, pady=10)

    def clear_database(self):
        if messagebox.askyesno("Warnung", "Bist du sicher, dass du die komplette Datenbank löschen möchtest?"):
            self.cursor.execute("DELETE FROM tracks")
            self.conn.commit()
            self.load_left_list('A')
            self.load_tracks('A')
            self.load_left_list('B')
            self.load_tracks('B')
            self.log("Datenbank wurde vollständig geleert.")

    def backup_database(self):
        dest = filedialog.asksaveasfilename(defaultextension=".db", filetypes=[("SQLite Database", "*.db")],
                                            initialfile="dj_library_backup.db")
        if dest:
            try:
                shutil.copy2(DB_FILE, dest)
                messagebox.showinfo("Backup", f"Datenbank erfolgreich gesichert unter:\n{dest}")
            except Exception as e:
                messagebox.showerror("Fehler", f"Backup fehlgeschlagen:\n{e}")

    def restore_database(self):
        src = filedialog.askopenfilename(filetypes=[("SQLite Database", "*.db"), ("Alle Dateien", "*.*")])
        if src:
            if messagebox.askyesno("Wiederherstellen", "Die aktuelle Datenbank wird überschrieben. Fortfahren?"):
                try:
                    self.conn.close()
                    shutil.copy2(src, DB_FILE)
                    self.init_db()
                    self.load_left_list('A')
                    self.load_tracks('A')
                    self.load_left_list('B')
                    self.load_tracks('B')
                    messagebox.showinfo("Wiederherstellung", "Datenbank erfolgreich wiederhergestellt.")
                    self.log("Datenbank aus Backup wiederhergestellt.")
                except Exception as e:
                    messagebox.showerror("Fehler", f"Wiederherstellung fehlgeschlagen:\n{e}")
                    self.init_db()

    def normalize_text(self, text):
        if not text: return ""
        text = text.replace("´", "'").replace("`", "'").replace("’", "'").replace("‘", "'")
        return text.strip()

    def add_library_folder(self, listbox):
        folder = filedialog.askdirectory()
        if folder:
            listbox.insert(tk.END, folder)
            self.save_settings()

    def remove_library_folder(self, listbox):
        selection = listbox.curselection()
        if selection:
            listbox.delete(selection[0])
            self.save_settings()

    def browse_folder(self, string_var):
        folder = filedialog.askdirectory()
        if folder: string_var.set(folder)

    def log(self, message):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')
        self.root.update()

    def update_grouping_mode(self, lib_id):
        v = self.views[lib_id]
        mode = v['grouping_var'].get()
        if mode == "artist_album":
            v['left_frame'].config(text="Künstler")
            v['left_tree'].heading("item", text="Alle Künstler")
            v['right_frame'].config(text="Alben")
            v['right_tree'].heading("item", text="Alle Alben")
        else:
            v['left_frame'].config(text="Alben")
            v['left_tree'].heading("item", text="Alle Alben")
            v['right_frame'].config(text="Künstler")
            v['right_tree'].heading("item", text="Alle Künstler")
        self.load_left_list(lib_id)
        self.load_tracks(lib_id)

    def load_left_list(self, lib_id):
        v = self.views[lib_id]
        for row in v['left_tree'].get_children(): v['left_tree'].delete(row)
        for row in v['right_tree'].get_children(): v['right_tree'].delete(row)

        mode = v['grouping_var'].get()
        if mode == "artist_album":
            v['left_tree'].insert("", "end", values=("(Alle Künstler)",))
            self.cursor.execute(
                'SELECT DISTINCT artist FROM tracks WHERE library_id=? AND artist != "" ORDER BY artist COLLATE NOCASE',
                (lib_id,))
            v['right_tree'].insert("", "end", values=("(Alle Alben)",))
        else:
            v['left_tree'].insert("", "end", values=("(Alle Alben)",))
            self.cursor.execute(
                'SELECT DISTINCT album FROM tracks WHERE library_id=? AND album != "" ORDER BY album COLLATE NOCASE',
                (lib_id,))
            v['right_tree'].insert("", "end", values=("(Alle Künstler)",))

        for row in self.cursor.fetchall():
            v['left_tree'].insert("", "end", values=(row[0],))

    def on_left_select(self, event, lib_id):
        v = self.views[lib_id]
        selection = v['left_tree'].selection()
        if not selection: return
        left_val = v['left_tree'].item(selection[0])['values'][0]
        mode = v['grouping_var'].get()

        for row in v['right_tree'].get_children(): v['right_tree'].delete(row)

        if mode == "artist_album":
            v['right_tree'].insert("", "end", values=("(Alle Alben)",))
            if left_val == "(Alle Künstler)":
                self.cursor.execute(
                    'SELECT DISTINCT album FROM tracks WHERE library_id=? AND album != "" ORDER BY album COLLATE NOCASE',
                    (lib_id,))
            else:
                self.cursor.execute(
                    'SELECT DISTINCT album FROM tracks WHERE library_id=? AND artist=? AND album != "" ORDER BY album COLLATE NOCASE',
                    (lib_id, left_val))
        else:
            v['right_tree'].insert("", "end", values=("(Alle Künstler)",))
            if left_val == "(Alle Alben)":
                self.cursor.execute(
                    'SELECT DISTINCT artist FROM tracks WHERE library_id=? AND artist != "" ORDER BY artist COLLATE NOCASE',
                    (lib_id,))
            else:
                self.cursor.execute(
                    'SELECT DISTINCT artist FROM tracks WHERE library_id=? AND album=? AND artist != "" ORDER BY artist COLLATE NOCASE',
                    (lib_id, left_val))

        for row in self.cursor.fetchall():
            v['right_tree'].insert("", "end", values=(row[0],))
        self.update_track_query(lib_id)

    def on_right_select(self, event, lib_id):
        self.update_track_query(lib_id)

    def update_track_query(self, lib_id):
        v = self.views[lib_id]
        left_sel = v['left_tree'].selection()
        right_sel = v['right_tree'].selection()

        left_val = v['left_tree'].item(left_sel[0])['values'][0] if left_sel else None
        right_val = v['right_tree'].item(right_sel[0])['values'][0] if right_sel else None

        mode = v['grouping_var'].get()
        artist, album = None, None

        if mode == "artist_album":
            if left_val and left_val != "(Alle Künstler)": artist = left_val
            if right_val and right_val != "(Alle Alben)": album = right_val
        else:
            if left_val and left_val != "(Alle Alben)": album = left_val
            if right_val and right_val != "(Alle Künstler)": artist = right_val

        self.load_tracks(lib_id, artist=artist, album=album)

    def on_search(self, event, lib_id):
        v = self.views[lib_id]
        query = v['search_entry'].get().strip()
        self.load_tracks(lib_id, search_query=query)

    def load_tracks(self, lib_id, artist=None, album=None, search_query=None):
        v = self.views[lib_id]
        for row in v['track_tree'].get_children(): v['track_tree'].delete(row)

        query = 'SELECT artist, album, track_num, title, duration, genre, year, bitrate, filename, filepath FROM tracks WHERE library_id=?'
        params = [lib_id]

        if artist:
            query += ' AND artist=?'
            params.append(artist)
        if album:
            query += ' AND album=?'
            params.append(album)
        if search_query:
            query += ' AND (title LIKE ? OR filename LIKE ?)'
            params.extend([f'%{search_query}%', f'%{search_query}%'])

        if v.get('missing_in_other_var') and v['missing_in_other_var'].get():
            other_lib = 'B' if lib_id == 'A' else 'A'
            query += f''' AND NOT EXISTS (
                SELECT 1 FROM tracks t2 
                WHERE t2.library_id='{other_lib}' 
                AND (tracks.filename = t2.filename OR (tracks.artist = t2.artist AND tracks.title = t2.title AND tracks.artist != '' AND tracks.title != ''))
            )'''

        if v['hide_dupes_var'].get():
            query += ' GROUP BY artist, title'

        query += ' ORDER BY artist, album, track_num'

        self.cursor.execute(query, tuple(params))

        for row in self.cursor.fetchall():
            row = list(row)
            row[4] = format_length(row[4])
            if row[7]: row[7] = f"{int(row[7])}"
            row.extend(["[ 📂 ]", "[ ▶ ]"])
            v['track_tree'].insert("", "end", values=row)

    def export_missing_report(self, lib_id):
        v = self.views[lib_id]
        items = v['track_tree'].get_children()
        if not items:
            messagebox.showinfo("Info", "Die aktuelle Ansicht ist leer.")
            return

        target_file = filedialog.asksaveasfilename(defaultextension=".txt", title="Report speichern",
                                                   initialfile=f"Inkonsistenz_Report_Lib_{lib_id}.txt")
        if not target_file: return

        with open(target_file, "w", encoding="utf-8") as f:
            other_lib = 'B' if lib_id == 'A' else 'A'
            f.write(f"--- Inkonsistenz-Report für Bibliothek {lib_id} ---\n")
            f.write(f"Diese {len(items)} Tracks fehlen potenziell in Bibliothek {other_lib}.\n\n")

            for item in items:
                vals = v['track_tree'].item(item, 'values')
                f.write(f"Artist: {vals[0]}\nTitle: {vals[3]}\nDateiname: {vals[8]}\nPfad: {vals[9]}\n")
                f.write("-" * 50 + "\n")

        messagebox.showinfo("Exportiert", f"Report mit {len(items)} Einträgen erfolgreich gespeichert.")

    def select_all_tracks(self, lib_id=None):
        if lib_id:
            v = self.views[lib_id]
            v['track_tree'].selection_add(v['track_tree'].get_children())
        return "break"

    def add_selected_to_sidelist(self, lib_id):
        v = self.views[lib_id]
        selected = v['track_tree'].selection()
        if not selected: return
        for item in selected:
            vals = v['track_tree'].item(item, 'values')
            v['sidelist'].insert("", "end", values=(vals[0], vals[3], vals[9], "[ 📂 ]", "[ ▶ ]"))

    def on_tree_double_click(self, event, lib_id):
        v = self.views[lib_id]
        region = v['track_tree'].identify("region", event.x, event.y)
        if region == "cell" and v['track_tree'].identify_column(event.x) not in ['#11', '#12']:
            item = v['track_tree'].identify_row(event.y)
            if item:
                vals = v['track_tree'].item(item, 'values')
                v['sidelist'].insert("", "end", values=(vals[0], vals[3], vals[9], "[ 📂 ]", "[ ▶ ]"))

    def remove_from_sidelist(self, event, lib_id):
        v = self.views[lib_id]
        if v['sidelist'].identify_column(event.x) not in ['#4', '#5']:
            for item in v['sidelist'].selection(): v['sidelist'].delete(item)

    def scan_libraries(self):
        folders_a = self.lib_listbox_a.get(0, tk.END)
        folders_b = self.lib_listbox_b.get(0, tk.END)

        if not folders_a and not folders_b:
            messagebox.showerror("Fehler", "Bitte mindestens einen Ordner hinzufügen!")
            return

        self.log("Starte Delta-Scan der Bibliotheken...")

        for lib_id, folders in [('A', folders_a), ('B', folders_b)]:
            if not folders: continue

            self.cursor.execute("SELECT filepath, filesize FROM tracks WHERE library_id=?", (lib_id,))
            existing_db = {row[0]: row[1] for row in self.cursor.fetchall()}

            found_files = set()
            new_count, updated_count = 0, 0

            self.log(f"Scanne Bibliothek {lib_id}...")
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
                            (filepath, filename, artist, title, album, genre, year, track_num, duration, filesize, bitrate, samplerate, library_id)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            filepath_str, filepath.name, artist, title, album, genre, year, track_num,
                            tag.duration, current_size, tag.bitrate, tag.samplerate, lib_id
                        ))
                        if filepath_str in existing_db:
                            updated_count += 1
                        else:
                            new_count += 1
                        if (new_count + updated_count) % 100 == 0:
                            self.log(f"  {new_count + updated_count} Dateien in {lib_id} indiziert...")
                    except:
                        pass

            missing_files = set(existing_db.keys()) - found_files
            for missing in missing_files:
                self.cursor.execute("DELETE FROM tracks WHERE filepath=? AND library_id=?", (missing, lib_id))

            self.log(
                f"Scan {lib_id} fertig! Neu: {new_count}, Aktualisiert: {updated_count}, Gelöscht: {len(missing_files)}")

        self.conn.commit()
        self.load_left_list('A')
        self.load_tracks('A')
        self.load_left_list('B')
        self.load_tracks('B')

    def export_sidelist(self, lib_id):
        v = self.views[lib_id]
        items = v['sidelist'].get_children()
        if not items: return

        do_copy, do_playlist = v['export_copy_var'].get(), v['export_playlist_var'].get()
        if not do_copy and not do_playlist:
            messagebox.showwarning("Warnung", "Bitte Export-Option auswählen.")
            return

        target_dir = filedialog.askdirectory(title="Zielordner auswählen")
        if not target_dir: return
        target_path = Path(target_dir)

        success_copy = 0
        playlist_entries = []
        for item in items:
            filepath = Path(v['sidelist'].set(item, "filepath"))
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
                with open(target_path / f"Sidelist_Lib_{lib_id}_Export.m3u", "w", encoding="utf-8") as f:
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
        self.log(f"Analysiere Dateien auf dem Stick (Referenz: Bibliothek A)...")

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
                self.cursor.execute("SELECT filepath FROM tracks WHERE library_id='A' AND artist=? AND title=? LIMIT 1",
                                    (c_artist, c_title))
                result = self.cursor.fetchone()
                if result: source_filepath, match_found = result[0], True

            if not match_found:
                self.cursor.execute("SELECT filepath FROM tracks WHERE library_id='A' AND filename=? LIMIT 1",
                                    (corrupted_file.name,))
                result = self.cursor.fetchone()
                if result: source_filepath, match_found = result[0], True

            if not match_found and c_artist and c_title:
                self.cursor.execute(
                    "SELECT filepath FROM tracks WHERE library_id='A' AND artist LIKE ? AND title LIKE ? LIMIT 1",
                    (f'%{c_artist}%', f'%{c_title}%'))
                result = self.cursor.fetchone()
                if result: source_filepath, match_found = result[0], True

            if not match_found:
                self.cursor.execute("SELECT filepath FROM tracks WHERE library_id='A' AND filename LIKE ? LIMIT 1",
                                    (f'%{corrupted_file.stem}%',))
                result = self.cursor.fetchone()
                if result: source_filepath, match_found = result[0], True

            if not match_found and "-" in corrupted_file.stem:
                parts = [p.strip() for p in corrupted_file.stem.split("-")]
                longest_part = max(parts, key=len)
                if len(longest_part) > 5:
                    self.cursor.execute("SELECT filepath FROM tracks WHERE library_id='A' AND filename LIKE ? LIMIT 1",
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

        match_cols = ("check", "filename", "src_path", "status", "corr_path_hidden", "folder_btn", "preview")
        match_tree = ttk.Treeview(match_frame, columns=match_cols, show='headings', selectmode='extended')
        match_tree.heading("check", text="Status")
        match_tree.heading("filename", text="Dateiname (auf Stick)")
        match_tree.heading("src_path", text="Quelle (Bibliothek A)")
        match_tree.heading("status", text="Info")
        match_tree.heading("folder_btn", text="Ort")
        match_tree.heading("preview", text="Play")

        match_tree.column("check", width=50, anchor='center')
        match_tree.column("filename", width=250)
        match_tree.column("src_path", width=350)
        match_tree.column("status", width=120)
        match_tree.column("corr_path_hidden", width=0, stretch=False)
        match_tree.column("folder_btn", width=40, anchor='center')
        match_tree.column("preview", width=40, anchor='center')

        self.make_tree_sortable(match_tree, match_cols)
        self.bind_actions(match_tree, '#6', '#7', 'src_path')

        mt_scroll = ttk.Scrollbar(match_frame, orient="vertical", command=match_tree.yview,
                                  style="Huge.Vertical.TScrollbar")
        match_tree.configure(yscrollcommand=mt_scroll.set)
        match_tree.pack(side='left', fill='both', expand=True, padx=(5, 0), pady=5)
        mt_scroll.pack(side='right', fill='y', ipadx=10, padx=(0, 5))

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
            match_tree.insert("", "end",
                              values=("\u2611", m_name, m_src_path, "Auto-Treffer", m_corr_path, "[ 📂 ]", "[ ▶ ]"))

        missing_frame = ttk.LabelFrame(paned,
                                       text=f"Fehlende Dateien ({len(missing_list)}) - Zum manuellen Suchen markieren")
        paned.add(missing_frame, weight=2)

        missing_cols = ("filename", "filepath", "folder_btn", "preview")
        missing_tree = ttk.Treeview(missing_frame, columns=missing_cols, show='headings')
        missing_tree.heading("filename", text="Dateiname (auf Stick)")
        missing_tree.heading("filepath", text="Absoluter Pfad")
        missing_tree.heading("folder_btn", text="Ort")
        missing_tree.heading("preview", text="Play")

        missing_tree.column("filename", width=300)
        missing_tree.column("filepath", width=400)
        missing_tree.column("folder_btn", width=40, anchor='center')
        missing_tree.column("preview", width=40, anchor='center')

        self.make_tree_sortable(missing_tree, missing_cols)
        self.bind_actions(missing_tree, '#3', '#4', 'filepath')

        ms_scroll = ttk.Scrollbar(missing_frame, orient="vertical", command=missing_tree.yview,
                                  style="Huge.Vertical.TScrollbar")
        missing_tree.configure(yscrollcommand=ms_scroll.set)
        missing_tree.pack(side='left', fill='both', expand=True, padx=(5, 0), pady=5)
        ms_scroll.pack(side='right', fill='y', ipadx=10, padx=(0, 5))

        for m_name, m_path in missing_list:
            missing_tree.insert("", "end", values=(m_name, m_path, "[ 📂 ]", "[ ▶ ]"))

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
        ttk.Button(action_frame, text="Reparatur für abgehakte Dateien JETZT ausführen", command=execute_repair).pack(
            fill='x', ipady=5)

    def open_manual_search_dialog(self, parent_popup, missing_tree, match_tree, missing_frame_ref):
        selected = missing_tree.selection()
        if not selected:
            messagebox.showinfo("Info", "Bitte zuerst eine Datei aus der unteren Liste auswählen.")
            return

        item = selected[0]
        corrupted_filename, corrupted_filepath, _, _ = missing_tree.item(item, 'values')

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

        res_cols = ("artist", "title", "kbps", "filename", "filepath", "folder_btn", "preview")
        result_tree = ttk.Treeview(search_popup, columns=res_cols, show='headings')
        result_tree.heading("artist", text="Künstler")
        result_tree.heading("title", text="Titel")
        result_tree.heading("kbps", text="kbps")
        result_tree.heading("filename", text="Dateiname")
        result_tree.heading("filepath", text="Pfad")
        result_tree.heading("folder_btn", text="Ort")
        result_tree.heading("preview", text="Play")

        result_tree.column("artist", width=120)
        result_tree.column("title", width=150)
        result_tree.column("kbps", width=50, anchor='center')
        result_tree.column("filename", width=150)
        result_tree.column("filepath", width=150)
        result_tree.column("folder_btn", width=40, anchor='center')
        result_tree.column("preview", width=40, anchor='center')

        self.make_tree_sortable(result_tree, res_cols)
        self.bind_actions(result_tree, '#6', '#7', 'filepath')

        def execute_manual_query(event=None):
            for row in result_tree.get_children(): result_tree.delete(row)
            q = s_entry.get().strip()
            self.cursor.execute('''
                                SELECT artist, title, bitrate, filename, filepath
                                FROM tracks
                                WHERE library_id = 'A'
                                  AND (filename LIKE ? OR artist LIKE ? OR title LIKE ?)
                                ''', (f'%{q}%', f'%{q}%', f'%{q}%'))
            for row in self.cursor.fetchall():
                r = list(row)
                if r[2]: r[2] = f"{int(r[2])}"
                r.extend(["[ 📂 ]", "[ ▶ ]"])
                result_tree.insert("", "end", values=r)

        execute_manual_query()
        s_entry.bind('<Return>', execute_manual_query)
        ttk.Button(top_frame, text="Suchen", command=execute_manual_query).pack(side='left', padx=5)

        res_scroll = ttk.Scrollbar(search_popup, orient="vertical", command=result_tree.yview,
                                   style="Huge.Vertical.TScrollbar")
        result_tree.configure(yscrollcommand=res_scroll.set)
        result_tree.pack(side='left', fill='both', expand=True, padx=(10, 0), pady=5)
        res_scroll.pack(side='right', fill='y', ipadx=10, padx=(0, 10))

        def apply_manual_match():
            sel_res = result_tree.selection()
            if not sel_res: return

            source_filepath = result_tree.item(sel_res[0], 'values')[4]
            missing_tree.delete(item)
            match_tree.insert("", "end", values=("\u2611", corrupted_filename, source_filepath, "Manuell verknüpft",
                                                 corrupted_filepath, "[ 📂 ]", "[ ▶ ]"))
            missing_frame_ref.config(
                text=f"Fehlende Dateien ({len(missing_tree.get_children())}) - Zum manuellen Suchen markieren")
            search_popup.destroy()

        ttk.Button(search_popup, text="Markierten Titel als Ersatz anwenden", command=apply_manual_match).pack(pady=10)

    # --- MP3val Integration ---
    def check_sidelist_mp3val(self, lib_id):
        v = self.views[lib_id]
        items = v['sidelist'].get_children()
        if not items:
            messagebox.showinfo("Info", "Die Sidelist ist leer.")
            return
        file_paths = [v['sidelist'].set(item, "filepath") for item in items]
        self.run_mp3val_check(file_paths, f"Sidelist (Lib {lib_id})")

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
        popup.geometry("1000x500")

        ttk.Label(popup, text="Überprüfe Dateien auf MPEG-Stream-Fehler und beschädigte Header...").pack(pady=10)

        cols = ("file", "status", "details", "filepath", "folder_btn", "preview")
        tree = ttk.Treeview(popup, columns=cols, show='headings')
        tree.heading("file", text="Datei")
        tree.heading("status", text="Status")
        tree.heading("details", text="Details")
        tree.heading("folder_btn", text="Ort")
        tree.heading("preview", text="Play")

        tree.column("file", width=350)
        tree.column("status", width=80, anchor='center')
        tree.column("details", width=300)
        tree.column("filepath", width=0, stretch=False)
        tree.column("folder_btn", width=40, anchor='center')
        tree.column("preview", width=40, anchor='center')

        self.make_tree_sortable(tree, cols)
        self.bind_actions(tree, '#5', '#6', 'filepath')

        scroll = ttk.Scrollbar(popup, orient="vertical", command=tree.yview, style="Huge.Vertical.TScrollbar")
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side='left', fill='both', expand=True, padx=(10, 0), pady=5)
        scroll.pack(side='right', fill='y', ipadx=10, padx=(0, 10))

        popup.update()
        corrupted_files = []

        for path in file_paths:
            try:
                result = subprocess.run([str(self.mp3val_path), path], capture_output=True, check=False)
                output = result.stdout.decode('cp1252', errors='replace')

                if "WARNING:" in output:
                    warning_detail = output.split("WARNING:")[-1].strip()
                    tree.insert("", "end", values=(Path(path).name, "FEHLER", warning_detail, path, "[ 📂 ]", "[ ▶ ]"))
                    corrupted_files.append(path)
                elif "ERROR:" in output:
                    error_detail = output.split("ERROR:")[-1].strip()
                    tree.insert("", "end", values=(Path(path).name, "KRITISCH", error_detail, path, "[ 📂 ]", "[ ▶ ]"))
                    corrupted_files.append(path)
                else:
                    tree.insert("", "end",
                                values=(Path(path).name, "OK", "Keine Fehler gefunden", path, "[ 📂 ]", "[ ▶ ]"))
            except Exception as e:
                tree.insert("", "end", values=(Path(path).name, "SYSTEM-FEHLER", str(e), path, "[ 📂 ]", "[ ▶ ]"))

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
        btn_fix = ttk.Button(btn_frame, text=f"Defekte Dateien reparieren ({len(corrupted_files)} gefunden)", command=fix_corrupted_files)
        btn_fix.pack(side='right', padx=5)
        if not corrupted_files: btn_fix.state(['disabled'])

if __name__ == "__main__":
    if DND_SUPPORTED:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
        print("Hinweis: Für externes Drag & Drop bitte 'pip install tkinterdnd2' ausführen.")

    app = DJRecoveryApp(root)
    root.mainloop()