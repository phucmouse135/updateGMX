import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import queue
import time
import math
import os
from concurrent.futures import ThreadPoolExecutor

# --- INTEGRATION IMPORTS ---
try:
    from config_utils import SafeWebDriver, ensure_chromedriver
    from ig_login import login_instagram_via_cookie
    from two_fa_handler import Instagram2FAStep
except ImportError as e:
    print(f"Backend modules missing: {e}")
    SafeWebDriver = None
    login_instagram_via_cookie = None
    Instagram2FAStep = None

class AutomationToolGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Instagram Automation Manager - Final Pro")
        self.root.geometry("1450x850")
        
        # Styles
        self.style = ttk.Style()
        self.style.theme_use('clam') 
        self.style.configure("Treeview", rowheight=28, font=('Arial', 9))
        self.style.configure("Treeview.Heading", font=('Arial', 10, 'bold'))
        self.style.configure("Bold.TButton", font=('Arial', 10, 'bold'))
        self.style.configure("Green.TLabel", foreground="green", font=('Arial', 10, 'bold'))
        self.style.configure("Red.TLabel", foreground="red", font=('Arial', 10, 'bold'))
        self.style.configure("Blue.TLabel", foreground="blue", font=('Arial', 10, 'bold'))
        
        # Variables
        self.file_path_var = tk.StringVar()
        self.thread_count_var = tk.IntVar(value=3)
        self.headless_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Ready")
        
        # Stats
        self.stats_total = tk.IntVar(value=0)
        self.stats_success = tk.IntVar(value=0)
        self.stats_fail = tk.IntVar(value=0)
        self.stats_running = tk.IntVar(value=0)
        self.stats_processed = tk.IntVar(value=0)

        # Threading & Queue
        self.is_running = False
        self.task_queue = queue.Queue()
        self.data_map = {} 
        self.window_slots = queue.Queue()
        self.driver_lock = threading.Lock()
        self.backup_lock = threading.Lock()
        
        # Screen Info
        self.screen_width = self.root.winfo_screenwidth()
        self.screen_height = self.root.winfo_screenheight()
        
        # --- DEFINING COLUMNS (14 CỘT) ---
        # ID(0) + 12 Cột Data + NOTE(13)
        self.columns = [
            "ID", "UID", "LINKED MAIL IG", "IG USER", "IG PASS", "2FA", 
            "ORIGINAL MAIL", "MAIL PASS", "RECOVERY MAIL", 
            "Post", "Followers", "Following", "COOKIE", "NOTE"
        ]

        if SafeWebDriver:
            threading.Thread(target=ensure_chromedriver, daemon=True).start()

        self.create_layout()

    def create_layout(self):
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # === 1. TOP SETTINGS ===
        top_frame = ttk.LabelFrame(main_frame, text=" ⚙️ Settings & Input ", padding=10)
        top_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(top_frame, text="Input File (.txt):").grid(row=0, column=0, padx=5, sticky="w")
        self.entry_file = ttk.Entry(top_frame, textvariable=self.file_path_var, width=60)
        self.entry_file.grid(row=0, column=1, padx=5, sticky="ew")
        
        btn_browse = ttk.Button(top_frame, text="📂 Browse", command=self.browse_file)
        btn_browse.grid(row=0, column=2, padx=5)
        
        btn_reload = ttk.Button(top_frame, text="🔄 Reload", command=self.reload_data)
        btn_reload.grid(row=0, column=3, padx=5)

        btn_paste = ttk.Button(top_frame, text="📝 Manual Input", command=self.open_manual_input, style="Bold.TButton")
        btn_paste.grid(row=0, column=4, padx=20)

        ttk.Label(top_frame, text="Threads:").grid(row=1, column=0, padx=5, pady=10, sticky="w")
        spin_threads = ttk.Spinbox(top_frame, from_=1, to=20, textvariable=self.thread_count_var, width=5)
        spin_threads.grid(row=1, column=1, padx=5, sticky="w")
        
        chk_headless = ttk.Checkbutton(top_frame, text="Headless Mode (Hide Browser)", variable=self.headless_var)
        chk_headless.grid(row=1, column=1, padx=100, sticky="w")

        top_frame.columnconfigure(1, weight=1)

        # === 2. DATA TABLE ===
        table_frame = ttk.Frame(main_frame)
        table_frame.pack(fill="both", expand=True)

        y_scroll = ttk.Scrollbar(table_frame, orient="vertical")
        x_scroll = ttk.Scrollbar(table_frame, orient="horizontal")

        self.tree = ttk.Treeview(
            table_frame, columns=self.columns, show="headings", 
            yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set,
            selectmode="extended"
        )
        
        y_scroll.config(command=self.tree.yview); y_scroll.pack(side="right", fill="y")
        x_scroll.config(command=self.tree.xview); x_scroll.pack(side="bottom", fill="x")
        self.tree.pack(side="left", fill="both", expand=True)

        col_widths = {
            "ID": 40, "UID": 100, "LINKED MAIL IG": 150, "IG USER": 120, 
            "IG PASS": 80, "2FA": 150, "ORIGINAL MAIL": 180, "MAIL PASS": 100, 
            "RECOVERY MAIL": 150, "Post": 40, "Followers": 50, "COOKIE": 100, "NOTE": 250
        }
        for col in self.columns:
            self.tree.heading(col, text=col, anchor="w")
            self.tree.column(col, width=col_widths.get(col, 100), anchor="w")

        self.tree.tag_configure("Success", background="#c3e6cb", foreground="#155724")
        self.tree.tag_configure("Fail", background="#f5c6cb", foreground="#721c24")
        self.tree.tag_configure("Running", background="#ffeeba", foreground="#856404")
        self.tree.tag_configure("Pending", background="white")

        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="📋 Copy Value", command=self.copy_cell_value)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="❌ Delete Row", command=self.delete_selected_rows)
        self.context_menu.add_command(label="🔄 Reset Status", command=self.reset_selected_rows)
        self.tree.bind("<Button-3>", self.show_context_menu)

        # === 3. BOTTOM ACTIONS ===
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill="x", pady=(10, 0))

        action_frame = ttk.LabelFrame(bottom_frame, text=" Actions ", padding=5)
        action_frame.pack(side="left", fill="y")
        ttk.Button(action_frame, text="❌ Delete Selected", command=self.delete_selected_rows).pack(side="left", padx=5)
        ttk.Button(action_frame, text="🗑️ Delete All", command=self.delete_all_rows).pack(side="left", padx=5)

        export_frame = ttk.LabelFrame(bottom_frame, text=" Export ", padding=5)
        export_frame.pack(side="left", fill="y", padx=10)
        ttk.Button(export_frame, text="💾 Export Success", command=lambda: self.export_data("Success")).pack(side="left", padx=5)
        ttk.Button(export_frame, text="💾 Export Failed", command=lambda: self.export_data("Fail")).pack(side="left", padx=5)
        ttk.Button(export_frame, text="💾 Export All", command=lambda: self.export_data("All")).pack(side="left", padx=5)

        exec_frame = ttk.Frame(bottom_frame)
        exec_frame.pack(side="right", fill="y")
        self.btn_start = ttk.Button(exec_frame, text="▶ START", command=self.start_process, style="Bold.TButton")
        self.btn_start.pack(side="left", padx=10, ipady=5)
        self.btn_stop = ttk.Button(exec_frame, text="⏹ STOP", command=self.stop_process, state="disabled")
        self.btn_stop.pack(side="left", padx=5, ipady=5)

        # === 4. STATUS BAR ===
        status_bar = ttk.Frame(self.root, relief="sunken", padding=5)
        status_bar.pack(side="bottom", fill="x")
        ttk.Label(status_bar, text="Status:").pack(side="left")
        ttk.Label(status_bar, textvariable=self.status_var, style="Blue.TLabel").pack(side="left", padx=5)
        ttk.Separator(status_bar, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Label(status_bar, text="Process:").pack(side="left")
        self.lbl_progress = ttk.Label(status_bar, text="0/0", font=('Arial', 9, 'bold'))
        self.lbl_progress.pack(side="left", padx=5)
        ttk.Separator(status_bar, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Label(status_bar, text="✅ Success:").pack(side="left")
        ttk.Label(status_bar, textvariable=self.stats_success, style="Green.TLabel").pack(side="left", padx=5)
        ttk.Label(status_bar, text="❌ Fail:").pack(side="left", padx=10)
        ttk.Label(status_bar, textvariable=self.stats_fail, style="Red.TLabel").pack(side="left", padx=5)

    # ================== HELPER METHODS ==================
    def browse_file(self):
        f = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt")])
        if f: self.file_path_var.set(f); self.load_data_from_file(f)

    def reload_data(self):
        if self.file_path_var.get(): self.load_data_from_file(self.file_path_var.get())

    def load_data_from_file(self, fpath):
        try:
            with open(fpath, "r", encoding="utf-8") as f: self.populate_table(f.read())
        except Exception as e: messagebox.showerror("Error", str(e))

    def populate_table(self, content, append=False):
        if not append: self.delete_all_rows(confirm=False); cnt = 0
        else: cnt = len(self.tree.get_children())
        lines = content.strip().split("\n")
        for line in lines:
            line = line.strip()
            if not line: continue
            parts = line.split("\t")
            
            # [FIX QUAN TRỌNG] Chỉ lấy 12 cột dữ liệu (từ UID đến COOKIE)
            # Nếu file thừa cột, cắt bỏ. Nếu thiếu, điền thêm.
            while len(parts) < 12: parts.append("")
            row_data = parts[:12] # Cắt đúng 12 cột để khớp với bảng
            
            cnt += 1
            
            # Kiểm tra cột 2FA (Index 4) để đánh dấu success có sẵn
            two_fa_data = row_data[4].strip()
            if "ERROR" in two_fa_data.upper():
                note = f"Failed: {two_fa_data.replace('ERROR_2FA:', '').strip()}"
                tag = "Fail"
            elif len(two_fa_data) > 5:
                note = "Done: skip"
                tag = "Success"
            else:
                note = "Pending"
                tag = "Pending"
            
            # [ID] + [12 DATA] + [NOTE] = 14 CỘT (Khớp 100% self.columns)
            iid = self.tree.insert("", "end", values=[cnt] + row_data + [note], tags=(tag,))
            self.data_map[iid] = row_data
        self.update_stats()

    def open_manual_input(self):
        win = tk.Toplevel(self.root); win.title("Paste Data"); win.geometry("900x600")
        txt = tk.Text(win); txt.pack(fill="both", expand=True)
        def submit():
            self.populate_table(txt.get("1.0", tk.END).strip(), append=True); win.destroy()
        ttk.Button(win, text="Submit", command=submit).pack()

    def calculate_window_rect(self, slot_id, max_slots, screen_width, screen_height):
        try:
            cols = math.ceil(math.sqrt(max_slots))
            if max_slots > 4: cols = 5
            rows = math.ceil(max_slots / cols)
            win_w = int(screen_width / cols); win_h = int((screen_height - 50) / rows)
            return ((slot_id % cols) * win_w, (slot_id // cols) * win_h, win_w, win_h)
        except: return None

    # ================== WORKER LOGIC ==================
    def worker_task(self, iid):
        if not self.is_running: return
        self.root.after(0, self.increment_running)
        
        start_time = time.time()
        
        row_data = list(self.data_map[iid])
        # Mapping dữ liệu: 
        # 0:UID, 1:LINK, 2:USER, 3:PASS, 4:2FA, 5:ORIG, 6:MPASS, 7:REC, 8:POST, 9:FLW, 10:FLG, 11:COOKIE
        username, password = row_data[2], row_data[3]
        gmx_user, gmx_pass = str(row_data[5]).strip(), str(row_data[6]).strip()
        linked_mail = str(row_data[1]).strip()
        
        # [FIX] Lấy Cookie ở index 11 (Cột thứ 12)
        cookie = row_data[11] if len(row_data) > 11 else ""
        
        if "@" not in gmx_user and len(gmx_user) > 0: gmx_user += "@gmx.net"

        self.root.after(0, lambda: self.update_row_status(iid, "Initializing...", "Running"))
        status, note, final_key = "Fail", "Unknown", ""
        slot_id = getattr(threading.current_thread(), "slot_id", 0)

        for attempt in range(2):
            try:
                rect = None
                if not self.headless_var.get():
                    rect = self.calculate_window_rect(slot_id, self.thread_count_var.get(), self.screen_width, self.screen_height)

                with SafeWebDriver(headless=self.headless_var.get(), window_rect=rect) as driver:
                    self.root.after(0, lambda: self.update_row_status(iid, "Logging in...", "Running"))
                    
                    # Login
                    login_ok, login_msg = login_instagram_via_cookie(driver, cookie)
                    
                    if login_ok:
                        # 2FA Setup
                        self.root.after(0, lambda: self.update_row_status(iid, "Setup 2FA...", "Running"))
                        try:
                            if Instagram2FAStep:
                                step = Instagram2FAStep(driver)
                                step.on_status_update = lambda msg: self.root.after(0, lambda: self.update_row_status(iid, msg, "Running"))
                                step.on_secret_key_found = lambda k: self.root.after(0, lambda: self.update_key_ui(iid, k))
                                result = step.setup_2fa(gmx_user, gmx_pass, username, linked_mail)
                            else: result = "Backend Missing"
                        except Exception as e: 
                            result = f"ERROR_EXCEPTION: {str(e)}"
                        
                        # Xử lý kết quả 2FA và Ghi NOTE
                        if result == "ALREADY_2FA_ON":
                            status, note, final_key = "Success", "Done: skip", "Already On"
                        elif str(result).startswith("ERROR") or "Exception" in str(result):
                            status = "Fail"
                            raw_err = str(result).replace("ERROR_2FA:", "").replace("STOP_FLOW_2FA:", "").strip()
                            note = f"{raw_err} {time.time() - start_time:.1f}s"  # Hiển thị chính xác mã lỗi + thời gian
                        else:
                            status, note, final_key = "Success", f"Done {time.time() - start_time:.1f}s", result
                            row_data[4] = final_key 
                    else:
                        # Xử lý lỗi Login và Ghi NOTE
                        status = "Fail"
                        note = f"{login_msg} {time.time() - start_time:.1f}s"  # Hiển thị chính xác mã lỗi + thời gian
                    
                    break

            except Exception as e:
                print(f"Task Error {username}: {e}")
                if attempt < 1: 
                    self.root.after(0, lambda: self.update_row_status(iid, f"Retrying...", "Running"))
                    time.sleep(2); continue
                status, note = "Fail", f"System Error/Crash {time.time() - start_time:.1f}s"

        self.data_map[iid] = row_data
        
        # [FIX] Đảm bảo Values hiển thị đúng 14 phần tử: ID + 12 Data + Note
        vals = [self.tree.item(iid, "values")[0]] + row_data + [note]
        
        self.root.after(0, lambda: self.update_row_status(iid, note, status, vals))
        self.root.after(0, self.update_count, status)
        
        # Ghi File Backup đầy đủ
        with self.backup_lock:
            fname = "success.txt" if status == "Success" else "fail.txt"
            try:
                with open(fname, "a", encoding="utf-8") as f:
                    f.write("\t".join(map(str, row_data + [note])) + "\n")
            except: pass
        self.root.after(0, self.decrement_running)

    def update_key_ui(self, iid, key):
         curr = list(self.tree.item(iid, "values"))
         if len(curr) > 5: curr[5] = key; self.tree.item(iid, values=curr)

    def update_row_status(self, iid, note, tag, new_vals=None):
        if self.tree.exists(iid):
            if new_vals: self.tree.item(iid, values=new_vals)
            else:
                curr = list(self.tree.item(iid, "values")); curr[-1] = note
                self.tree.item(iid, values=curr)
            self.tree.item(iid, tags=(tag,)); self.root.update_idletasks(); self.update_stats()

    def update_count(self, status):
        self.stats_processed.set(self.stats_processed.get() + 1)
        self.stats_running.set(self.stats_running.get() - 1)
        self.update_stats()
    
    def increment_running(self): self.stats_running.set(self.stats_running.get() + 1); self.update_stats()
    def decrement_running(self): self.stats_running.set(self.stats_running.get() - 1); self.update_stats()

    def update_stats(self):
        s = sum(1 for i in self.tree.get_children() if self.tree.item(i,"tags")[0]=="Success")
        f = sum(1 for i in self.tree.get_children() if self.tree.item(i,"tags")[0]=="Fail")
        self.stats_success.set(s); self.stats_fail.set(f)
        done = sum(1 for i in self.tree.get_children() if self.tree.item(i,"tags")[0]!="Pending")
        self.lbl_progress.config(text=f"{done}/{self.stats_total.get()}")

    def start_process(self):
        items = [i for i in self.tree.get_children() if self.tree.item(i,"tags")[0] not in ["Success", "Fail"]]
        if not items: return messagebox.showinfo("Info","No pending tasks.")
        self.is_running = True; self.btn_start.config(state="disabled"); self.btn_stop.config(state="normal")
        self.stats_processed.set(0); self.stats_total.set(len(items)); self.stats_running.set(0); self.update_stats()
        self.task_queue = queue.Queue(); [self.task_queue.put(i) for i in items]
        n_threads = self.thread_count_var.get()
        self.window_slots = queue.Queue(); [self.window_slots.put(i) for i in range(n_threads)]
        threading.Thread(target=self.run_workers, daemon=True).start()

    def run_workers(self):
        def worker_wrapper():
            while self.is_running:
                try:
                    iid = self.task_queue.get(timeout=1); slot = self.window_slots.get()
                    threading.current_thread().slot_id = slot
                    try: self.worker_task(iid)
                    finally: self.window_slots.put(slot); self.task_queue.task_done()
                except: break
        with ThreadPoolExecutor(max_workers=self.thread_count_var.get()) as ex:
            [ex.submit(worker_wrapper) for _ in range(self.thread_count_var.get())]
        self.is_running = False; self.root.after(0, self.finish_run)

    def finish_run(self):
        self.btn_start.config(state="normal"); self.btn_stop.config(state="disabled")
        self.status_var.set("Completed"); messagebox.showinfo("Done","Completed!")

    def stop_process(self):
        if messagebox.askyesno("Stop","Stop tasks?"): self.is_running = False

    def delete_selected_rows(self):
        for i in self.tree.selection():
            if self.tree.item(i,"tags")[0]!="Pending": self.stats_processed.set(self.stats_processed.get()-1)
            self.tree.delete(i); self.data_map.pop(i, None)
        self.stats_total.set(len(self.tree.get_children())); self.update_stats()

    def delete_all_rows(self, confirm=True):
        if confirm and not messagebox.askyesno("Clear","Clear all?"): return
        [self.tree.delete(i) for i in self.tree.get_children()]
        self.data_map.clear(); self.stats_total.set(0); self.stats_success.set(0); self.stats_fail.set(0); self.update_stats()

    def reset_selected_rows(self):
        [self.update_row_status(i, "Pending", "Pending") for i in self.tree.selection()]

    def show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item: self.tree.selection_set(item); self.clicked_item=item; self.clicked_col=self.tree.identify_column(event.x); self.context_menu.post(event.x_root, event.y_root)

    def copy_cell_value(self):
        try:
            col = int(self.clicked_col.replace("#",""))-1; val = self.tree.item(self.clicked_item,"values")[col]
            self.root.clipboard_clear(); self.root.clipboard_append(val)
        except: pass

    def export_data(self, mode):
        f = filedialog.asksaveasfilename(defaultextension=".txt")
        if not f: return
        with open(f,"w",encoding="utf-8") as file:
            for i in self.tree.get_children():
                st = self.tree.item(i,"tags")[0]
                if mode=="All" or (mode=="Success" and st=="Success") or (mode=="Fail" and st=="Fail"):
                    file.write("\t".join(map(str, self.data_map[i]+[self.tree.item(i,"values")[-1]]))+"\n")
        messagebox.showinfo("Export","Done!")

if __name__ == "__main__":
    root = tk.Tk(); app = AutomationToolGUI(root); root.mainloop()