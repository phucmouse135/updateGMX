import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import queue
import time
from concurrent.futures import ThreadPoolExecutor

# --- INTEGRATION IMPORTS ---
try:
    from config_utils import get_driver, ensure_chromedriver
    from ig_login import login_instagram_via_cookie
    from two_fa_handler import setup_2fa
except ImportError:
    print("Backend modules missing (Running UI-only mode)")
    get_driver = None
    login_instagram_via_cookie = None
    setup_2fa = None

class AutomationToolGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Instagram Automation Manager - Pro Edition")
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
        self.headless_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Ready")
        
        self.stats_total = tk.IntVar(value=0)
        self.stats_success = tk.IntVar(value=0)
        self.stats_fail = tk.IntVar(value=0)
        self.stats_running = tk.IntVar(value=0)  # Số tiến trình đang chạy
        self.stats_processed = tk.IntVar(value=0)  # Số tiến trình đã hoàn thành

        self.is_running = False
        self.task_queue = queue.Queue()
        self.data_map = {} 
        
        # --- DEFINING COLUMNS (12 INPUT COLUMNS + ID + NOTE) ---
        # 0:UID, 1:MAIL_LK, 2:USER, 3:PASS, 4:2FA, 5:PHOIGOC, 6:PASSMAIL, ...
        self.columns = [
            "ID", "UID", "LINKED MAIL IG", "IG USER", "IG PASS", "2FA", 
            "ORIGINAL MAIL", "MAIL PASS", "RECOVERY MAIL", 
            "Post", "Followers", "Following", "COOKIE", "NOTE"
        ]

        if get_driver:
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
        spin_threads = ttk.Spinbox(top_frame, from_=1, to=50, textvariable=self.thread_count_var, width=5)
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
        
        y_scroll.config(command=self.tree.yview)
        x_scroll.config(command=self.tree.xview)
        y_scroll.pack(side="right", fill="y")
        x_scroll.pack(side="bottom", fill="x")
        self.tree.pack(side="left", fill="both", expand=True)

        # Columns Config
        col_widths = {
            "ID": 40, "UID": 100, "MAIL LK IG": 150, "IG USER": 120, 
            "PASS IG": 80, "2FA": 150, "PHÔI GỐC": 180, "PASS MAIL": 100, 
            "MAIL KHÔI PHỤC": 150, "Post": 40, "Followers": 50, "COOKIE": 100, "NOTE": 250
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
        ttk.Button(export_frame, text="💾 Export NotSuccess", command=lambda: self.export_data("NoSuccess")).pack(side="left", padx=5)

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

    # ================== MANUAL INPUT ==================
    def open_manual_input(self):
        win = tk.Toplevel(self.root)
        win.title("Paste Data (Tab-separated)")
        win.geometry("900x600")
        
        main_cont = ttk.Frame(win, padding=10)
        main_cont.pack(fill="both", expand=True)

        ttk.Label(main_cont, text="Paste data here (Copy from Excel/Text):", font=("Arial", 10, "bold")).pack(anchor="w")

        txt_frame = ttk.Frame(main_cont)
        txt_frame.pack(fill="both", expand=True, pady=5)

        v_scroll = ttk.Scrollbar(txt_frame, orient="vertical")
        h_scroll = ttk.Scrollbar(txt_frame, orient="horizontal")
        
        self.txt_manual = tk.Text(txt_frame, wrap="none", font=("Consolas", 10), 
                                  yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)
        
        v_scroll.config(command=self.txt_manual.yview)
        h_scroll.config(command=self.txt_manual.xview)
        
        v_scroll.pack(side="right", fill="y")
        h_scroll.pack(side="bottom", fill="x")
        self.txt_manual.pack(side="left", fill="both", expand=True)

        btn_panel = ttk.Frame(main_cont)
        btn_panel.pack(fill="x", pady=5)

        def do_import():
            data = self.txt_manual.get("1.0", tk.END).strip()
            if data:
                self.populate_table(data, append=True)
                win.destroy()
                messagebox.showinfo("Success", "Data imported!")
            else:
                messagebox.showwarning("Warning", "Data is empty")

        ttk.Button(btn_panel, text="📥 Import Data", command=do_import, style="Bold.TButton").pack(side="right", padx=5)
        ttk.Button(btn_panel, text="🗑️ Clear", command=lambda: self.txt_manual.delete("1.0", tk.END)).pack(side="right", padx=5)
        ttk.Button(btn_panel, text="Cancel", command=win.destroy).pack(side="left")

    # ================== DATA LOGIC ==================
    def browse_file(self):
        f = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt")])
        if f:
            self.file_path_var.set(f)
            self.load_data_from_file(f)

    def reload_data(self):
        if self.file_path_var.get(): self.load_data_from_file(self.file_path_var.get())

    def load_data_from_file(self, fpath):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                self.populate_table(f.read())
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def populate_table(self, content, append=False):
        if not append:
            self.delete_all_rows(confirm=False)
            cnt = 0
        else:
            cnt = len(self.tree.get_children())

        lines = content.strip().split("\n")
        for line in lines:
            line = line.strip()
            if not line: continue
            
            parts = line.split("\t")
            # Ensure 12 columns
            while len(parts) < 12: parts.append("")
            
            row_data = parts[:12]
            
            cnt += 1
            # Add ID/Note
            row_display_vals = [cnt] + row_data + ["Pending"]
            
            iid = self.tree.insert("", "end", values=row_display_vals, tags=("Pending",))
            
            self.data_map[iid] = row_data

        self.update_stats()

    # ================== WORKER LOGIC (12 COLS MAPPING) ==================
    def worker_task(self, iid):
        if not self.is_running:
            return

        # Khi bắt đầu thực sự chạy, tăng số running
        self.root.after(0, lambda: self.update_running_count(1))

        # Load Raw Data (12 Cols)
        row_data = list(self.data_map[iid])
        mail_lk = str(row_data[1]).strip()
        username = row_data[2]
        gmx_user = str(row_data[5]).strip()
        gmx_pass = str(row_data[6]).strip()
        cookie = row_data[11]

        # Auto fix domain GMX
        if "@" not in gmx_user and len(gmx_user) > 0:
            gmx_user = f"{gmx_user}@gmx.net"

        self.root.after(0, lambda: self.update_row_status(iid, "Running...", "Running"))

        status, note = "Fail", "Unknown"
        driver = None

        try:
            if not get_driver:
                raise ImportError("Backend missing")
            driver = get_driver(headless=self.headless_var.get())
            if login_instagram_via_cookie(driver, cookie):
                self.root.after(0, lambda: self.update_row_status(iid, "2FA Setup...", "Running"))
                new_key = setup_2fa(
                    driver,
                    email=gmx_user,
                    email_pass=gmx_pass,
                    target_username=username,
                    linked_email=mail_lk
                )
                if new_key:
                    status = "Success"
                    note = "Done"
                    row_data[4] = new_key  # Update 2FA
                else:
                    note = "2FA Failed (No Key)"
            else:
                note = "Login Failed / Cookie Die"
        except Exception as e:
            msg = str(e)
            if "RESTRICTED" in msg:
                note = "Restricted"
            elif "authentication failed" in msg.lower():
                note = "GMX Login Fail"
            elif "WRONG EMAIL HINT" in msg:
                note = "Wrong Hint (Both Mails)"
            else:
                note = msg
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass

        # Save & Update UI
        self.data_map[iid] = row_data
        final_ui_vals = [self.tree.item(iid, "values")[0]] + row_data + [note]
        self.root.after(0, lambda: self.update_row_status(iid, note, status, final_ui_vals))
        self.root.after(0, self.update_count, status)
        # Khi kết thúc, giảm số running
        self.root.after(0, lambda: self.update_running_count(-1))

    def update_running_count(self, delta):
        val = self.stats_running.get() + delta
        if val < 0:
            val = 0
        self.stats_running.set(val)
        self.update_stats()

    # ================== UI UPDATES & UTILS ==================
    def update_row_status(self, iid, note, tag, new_vals=None):
        if self.tree.exists(iid):
            if new_vals: self.tree.item(iid, values=new_vals)
            else:
                curr = list(self.tree.item(iid, "values"))
                curr[-1] = note
                self.tree.item(iid, values=curr)
            self.tree.item(iid, tags=(tag,))
            self.tree.see(iid)

    def update_count(self, status):
        self.stats_processed.set(self.stats_processed.get() + 1)
        self.stats_running.set(self.stats_running.get() - 1)
        if status == "Success":
            self.stats_success.set(self.stats_success.get() + 1)
        else:
            self.stats_fail.set(self.stats_fail.get() + 1)
        self.update_stats()

    def update_stats(self):
        running = self.stats_running.get()
        # Số tiến trình đã chạy xong + số tiến trình đang chạy (kể cả Running và các bước sau) / tổng số tiến trình
        done_and_running = 0
        for iid in self.tree.get_children():
            status = self.tree.item(iid, "tags")[0]
            if status != "Pending":
                done_and_running += 1
        self.lbl_progress.config(text=f"{done_and_running}/{self.stats_total.get()}")

    def start_process(self):
        items = [i for i in self.tree.get_children() if self.tree.item(i, "values")[-1] != "Success" and self.tree.item(i, "values")[-1] != "2FA_EXISTS"]
        if not items:
            return messagebox.showinfo("Info", "No pending tasks.")

        self.is_running = True
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.status_var.set("Running...")
        self.stats_success.set(0)
        self.stats_fail.set(0)
        self.stats_processed.set(0)
        self.stats_total.set(len(items))
        self.stats_running.set(0)  # Số tiến trình thực sự đang chạy
        self.update_stats()

        self.task_queue = queue.Queue()
        for i in items:
            self.task_queue.put(i)

        threading.Thread(target=self.run_workers, daemon=True).start()

    def run_workers(self):
        with ThreadPoolExecutor(max_workers=self.thread_count_var.get()) as ex:
            while self.is_running and not self.task_queue.empty():
                try:
                    iid = self.task_queue.get(timeout=1)
                    ex.submit(self.worker_task, iid)
                except: break
        self.is_running = False
        self.root.after(0, self.finish_run)

    def finish_run(self):
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.status_var.set("Completed")
        messagebox.showinfo("Done", "Process Finished.")

    def stop_process(self):
        if messagebox.askyesno("Stop", "Stop all tasks?"):
            self.is_running = False
            self.status_var.set("Stopping...")

    def delete_selected_rows(self):
        for i in self.tree.selection():
            self.tree.delete(i)
            if i in self.data_map: del self.data_map[i]
        self.update_stats_total()

    def delete_all_rows(self, confirm=True):
        if confirm and not messagebox.askyesno("Clear", "Delete all rows?"): return
        for i in self.tree.get_children(): self.tree.delete(i)
        self.data_map = {}
        self.update_stats_total()

    def update_stats_total(self):
        self.stats_total.set(len(self.tree.get_children()))
        self.update_stats()

    def reset_selected_rows(self):
        for i in self.tree.selection():
            self.update_row_status(i, "Pending", "Pending")

    def show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.clicked_item = item
            self.clicked_col = self.tree.identify_column(event.x)
            self.context_menu.post(event.x_root, event.y_root)

    def copy_cell_value(self):
        try:
            col = int(self.clicked_col.replace("#", "")) - 1
            val = self.tree.item(self.clicked_item, "values")[col]
            self.root.clipboard_clear()
            self.root.clipboard_append(val)
        except: pass

    def export_data(self, mode):
        f = filedialog.asksaveasfilename(defaultextension=".txt")
        if not f: return
        try:
            with open(f, "w", encoding="utf-8") as file:
                for iid in self.tree.get_children():
                    raw = self.data_map.get(iid)
                    if not raw: continue
                    status = self.tree.item(iid, "tags")[0]
                    save = False
                    if mode == "All":
                        save = True
                    elif mode == "Success" and status == "Success":
                        save = True
                    elif mode == "Fail" and status == "Fail":
                        save = True
                    elif mode == "NoSuccess":
                        # NotSuccess: not Success and not Pending
                        if status != "Success" and status != "Pending" and status != "Done":
                            save = True
                    if save:
                        file.write("\t".join(raw) + "\n")
            messagebox.showinfo("Export", "Done!")
        except Exception as e:
            messagebox.showerror("Error", str(e))

if __name__ == "__main__":
    root = tk.Tk()
    app = AutomationToolGUI(root)
    root.mainloop()