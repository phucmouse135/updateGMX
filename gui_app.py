import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import queue
import time
from concurrent.futures import ThreadPoolExecutor

# Import existing logic from project
from config_utils import get_driver, ensure_chromedriver
from ig_login import login_instagram_via_cookie
from two_fa_handler import setup_2fa

class Instagram2FAToolApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Instagram Auto 2FA Tool - Pro GUI")
        self.root.geometry("1400x800") # Expanded for columns

        # --- Variables ---
        self.file_path = "input.txt" # Default
        self.is_running = False
        self.task_queue = queue.Queue()
        self.executor = None
        self.stop_event = threading.Event()
        self.results_lock = threading.Lock()
        
        # Stats
        self.total_input = 0
        self.running_count = 0
        self.success_count = 0
        self.processed_count = 0
        
        # --- UI Layout ---
        self.setup_top_controls()
        self.setup_tables()
        self.setup_status_bar()

    def setup_top_controls(self):
        frame = ttk.LabelFrame(self.root, text="Configuration & Controls", padding=10)
        frame.pack(fill="x", padx=10, pady=5)

        # Row 0: File Input & Data Loading
        ttk.Label(frame, text="File Input (Optional):").grid(row=0, column=0, padx=5, sticky="w")
        self.entry_file = ttk.Entry(frame, width=40)
        self.entry_file.insert(0, self.file_path)
        self.entry_file.grid(row=0, column=1, padx=5)
        ttk.Button(frame, text="Choose File", command=self.browse_file).grid(row=0, column=2, padx=5)
        ttk.Button(frame, text="Load Data", command=self.load_data).grid(row=0, column=3, padx=5)
        ttk.Button(frame, text="Manual Input", command=self.open_manual_input).grid(row=0, column=4, padx=5)

        # Row 1: Running Controls & Stats
        frame_run = ttk.Frame(frame)
        frame_run.grid(row=1, column=0, columnspan=10, sticky="w", pady=10)
        
        ttk.Label(frame_run, text="Threads:").pack(side="left", padx=(5, 5))
        self.spin_threads = ttk.Spinbox(frame_run, from_=1, to=50, width=5)
        self.spin_threads.set(1)
        self.spin_threads.pack(side="left", padx=5)

        self.btn_start = ttk.Button(frame_run, text="▶ START", command=self.start_process)
        self.btn_start.pack(side="left", padx=10)
        
        self.btn_stop = ttk.Button(frame_run, text="⏹ STOP", command=self.stop_process, state="disabled")
        self.btn_stop.pack(side="left", padx=5)
        
        # Checkbox Run Hidden
        self.var_headless = tk.BooleanVar(value=False)
        self.chk_headless = ttk.Checkbutton(frame_run, text="Headless Mode", variable=self.var_headless)
        self.chk_headless.pack(side="left", padx=10)
        
        # Stats Labels
        ttk.Separator(frame_run, orient="vertical").pack(side="left", fill="y", padx=10)
        
        self.lbl_progress = ttk.Label(frame_run, text="Progress: 0/0", font=("Arial", 9, "bold"))
        self.lbl_progress.pack(side="left", padx=10)
        
        self.lbl_running = ttk.Label(frame_run, text="Running: 0", foreground="blue")
        self.lbl_running.pack(side="left", padx=10)
        
        self.lbl_success = ttk.Label(frame_run, text="Success: 0", foreground="green")
        self.lbl_success.pack(side="left", padx=10)

    def setup_tables(self):
        # Main frame for table
        frame_main = ttk.Frame(self.root)
        frame_main.pack(fill="both", expand=True, padx=10, pady=5)

        # ==========================================
        # INPUT TABLE (NOW MAIN TABLE)
        # ==========================================
        frame_input = ttk.LabelFrame(frame_main, text="Account List", padding=5)
        frame_input.pack(fill="both", expand=True)
        
        # Toolbar Input
        tb_input = ttk.Frame(frame_input)
        tb_input.pack(side="top", fill="x", pady=2)
        ttk.Button(tb_input, text="Delete Selected", command=self.delete_selected_input).pack(side="left", padx=2)
        ttk.Button(tb_input, text="Delete All", command=self.delete_all_input).pack(side="left", padx=2)
        
        # Changed Export buttons here
        ttk.Separator(tb_input, orient="vertical").pack(side="left", fill="y", padx=5)
        ttk.Button(tb_input, text="Export All", command=self.export_all).pack(side="left", padx=2)
        ttk.Button(tb_input, text="Export Success", command=self.export_success).pack(side="left", padx=2)
        ttk.Button(tb_input, text="Export FAIL/PENDING", command=self.export_fail).pack(side="left", padx=2)
        ttk.Button(tb_input, text="Export FAIL Only", command=self.export_fail_only).pack(side="left", padx=2)

        # Define columns
        self.cols_def = ["ID", "User", "PASS", "2FA", "Email", "Pass Email", "Post", "Followers", "Following", "COOKIE", "Note"]
        
        self.tree_input = ttk.Treeview(frame_input, columns=self.cols_def, show="headings", height=20)
        
        # Config Columns
        col_widths = [40, 120, 100, 100, 180, 100, 50, 70, 70, 100, 200]
        for i, col in enumerate(self.cols_def):
            self.tree_input.heading(col, text=col)
            self.tree_input.column(col, width=col_widths[i], anchor="w")
        self.tree_input.column("ID", anchor="center")

        scroll_in_y = ttk.Scrollbar(frame_input, orient="vertical", command=self.tree_input.yview)
        scroll_in_x = ttk.Scrollbar(frame_input, orient="horizontal", command=self.tree_input.xview)
        self.tree_input.configure(yscroll=scroll_in_y.set, xscroll=scroll_in_x.set)
        
        self.tree_input.pack(side="left", fill="both", expand=True)
        scroll_in_y.pack(side="right", fill="y")
        scroll_in_x.pack(side="bottom", fill="x")

        # Tag configuration
        self.tree_input.tag_configure("pending", background="white")
        self.tree_input.tag_configure("running", background="#fffacd") # Vàng nhạt
        self.tree_input.tag_configure("success", background="#e0ffe0") # Xanh nhạt
        self.tree_input.tag_configure("fail", background="#ffe0e0")    # Đỏ nhạt

    def setup_status_bar(self):
        self.status_var = tk.StringVar(value="Ready")
        lbl_status = ttk.Label(self.root, textvariable=self.status_var, relief="sunken", anchor="w")
        lbl_status.pack(side="bottom", fill="x")

    def browse_file(self):
        f = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")])
        if f:
            self.entry_file.delete(0, tk.END)
            self.entry_file.insert(0, f)
            self.load_data()

    def load_data(self):
        # Clear old
        self.delete_all_input()
        
        path = self.entry_file.get()
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            self._parse_and_add_lines(lines)
        except Exception as e:
            messagebox.showerror("File Error", str(e))

    def open_manual_input(self):
        # Create popup
        top = tk.Toplevel(self.root)
        top.title("Manual Data Input")
        top.geometry("700x500")
        
        lbl_hint = ttk.Label(top, text="Paste data in format (Tab separated):\nUser | Pass | 2FA | Email | PassMail | Post | Flwer | Flwing | Cookie", justify="left")
        lbl_hint.pack(anchor="w", padx=10, pady=5)
        
        txt_input = tk.Text(top, height=20)
        txt_input.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Sample placeholder
        txt_input.insert("1.0", "# Example:\nusername\tpassword\t\temail@mail.com\tmailpass\t0\t0\t0\tcookie_string...")
        
        def _confirm():
            content = txt_input.get("1.0", tk.END)
            # Filter comments
            lines = [l for l in content.split("\n") if l.strip() and not l.strip().startswith("#")]
            self._parse_and_add_lines(lines)
            top.destroy()
            
        ttk.Button(top, text="Add to List", command=_confirm).pack(pady=10)


    def _parse_and_add_lines(self, lines):
        count = len(self.tree_input.get_children())
        if not hasattr(self, 'data_map'): self.data_map = {}
        
        for line in lines:
            line = line.strip()
            if not line: continue
            parts = line.split("\t")
            
            # Normalize length
            while len(parts) < 9: parts.append("")
            
            # Mapping: User[0], Pass[1], 2FA[2], Email[3], PassEmail[4], Post[5], Follow[6], Following[7], Cookie[8]
            username = parts[0]
            
            row_vals = [
                count + 1,
                parts[0], # User
                parts[1], # Pass
                parts[2], # 2FA 
                parts[3], # Email
                parts[4], # EAPass
                parts[5], # Post
                parts[6], # Follower
                parts[7], # Following
                parts[8], # Cookie
                "Pending" # Note
            ]
            
            # Insert to input table
            iid = str(count)
            self.tree_input.insert("", "end", iid=iid, values=row_vals, tags=("pending",))
            
            # Save raw data
            self.data_map[iid] = parts
            count += 1
            
        self.total_input = count
        self.update_progress_ui()
        self.status_var.set(f"Loaded {count} lines.")

    def delete_selected_input(self):
        selected_items = self.tree_input.selection()
        for iid in selected_items:
            self.tree_input.delete(iid)
            if iid in self.data_map:
                del self.data_map[iid]
        self.total_input = len(self.tree_input.get_children())
        self.update_progress_ui()

    def delete_all_input(self):
        for item in self.tree_input.get_children():
            self.tree_input.delete(item)
        self.data_map = {}
        self.total_input = 0
        self.update_progress_ui()

    def export_all(self):
        # Export all, no filter
        self._export_data(lambda tags: True, "ALL")

    def export_success(self):
        # Export rows with tag 'success'
        self._export_data(lambda tags: "success" in tags, "SUCCESS")

    def export_fail(self):
        # Export rows WITHOUT tag 'success' (including pending, fail, running...)
        self._export_data(lambda tags: "success" not in tags, "FAIL_PENDING")

    def export_fail_only(self):
        # Export rows chỉ có tag 'fail' (không bao gồm pending/running)
        self._export_data(lambda tags: ("fail" in tags) and ("success" not in tags), "FAIL_ONLY")

    def _export_data(self, condition_func, suffix):
        try:
            filename = f"output_{suffix}_{int(time.time())}.txt"
            f = filedialog.asksaveasfilename(
                initialfile=filename,
                defaultextension=".txt", 
                filetypes=[("Text Files", "*.txt")]
            )
            if not f: return
            
            count = 0
            with open(f, "w", encoding="utf-8") as file:
                # No header writing
                
                # Write rows matching condition
                for child in self.tree_input.get_children():
                    tags = self.tree_input.item(child)["tags"]
                    
                    if condition_func(tags):
                        vals = self.tree_input.item(child)["values"]
                        
                        # TreeView: ID[0], User[1], Pass[2], 2FA[3], Email[4], PassEmail[5], Post[6], Follow[7], Following[8], Cookie[9], Note[10]
                        # Need Input (9 col): User ... Cookie 
                        # -> slice [1:10] (index 1 to 9)
                        
                        export_vals = vals[1:10] 
                        line = "\t".join([str(v) for v in export_vals])
                        file.write(line + "\n")
                        count += 1
            
            messagebox.showinfo("Success", f"Exported {count} rows of {suffix}!")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def update_progress_ui(self):
        with self.results_lock:
            processed = self.processed_count
            total = self.total_input
            running = self.running_count
            success = self.success_count
        self.lbl_progress.config(text=f"Progress: {processed}/{total}")
        self.lbl_running.config(text=f"Running: {running}")
        self.lbl_success.config(text=f"Success: {success}")

    def start_process(self):
        if self.is_running: return
        
        # Reset counts for new run session (optional, or keep accumulating?)
        # Let's reset session counters but keep total
        with self.results_lock:
            self.processed_count = 0
            self.success_count = 0
            self.running_count = 0
        self.update_progress_ui()
        
        # Get pending items
        items = self.tree_input.get_children()
        if not items:
            messagebox.showwarning("Cảnh báo", "Chưa có dữ liệu input!")
            return

        threads_count = int(self.spin_threads.get())
        
        self.is_running = True
        self.stop_event.clear()
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.status_var.set(f"Dang chay voi {threads_count} luong...")

        # Lưu trạng thái Headless cho phiên chạy này để các thread con sử dụng
        self.current_headless_mode = self.var_headless.get()

        # Reset queue
        self.task_queue = queue.Queue()
        for iid in items:
            # Chỉ chạy những dòng chưa hoàn thành hoặc chưa có kết quả "ALREADY_2FA_ON"
            curr_vals = self.tree_input.item(iid, "values")
            # Note is index 10
            status_note = str(curr_vals[10]) # Chuyển thành string cho chắc
            
            # Skip logic: Nếu "Thành công" HOẶC "ALREADY_2FA_ON" nằm trong note -> Bỏ qua
            if "Thành công" in status_note or "ALREADY_2FA_ON" in status_note:
                continue
                
            self.task_queue.put(iid)

        # Start Workers
        threading.Thread(target=self.run_thread_pool, args=(threads_count,), daemon=True).start()

    def run_thread_pool(self, max_workers):
        ensure_chromedriver()
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            while not self.task_queue.empty() and not self.stop_event.is_set():
                if self.stop_event.is_set():
                    break
                try:
                    iid = self.task_queue.get_nowait()
                    futures.append(executor.submit(self.process_one_account, iid))
                except queue.Empty:
                    break

            for f in futures:
                if self.stop_event.is_set():
                    break
                f.result()

        self.root.after(0, self.on_finish)

    def process_one_account(self, iid):
        if self.stop_event.is_set(): return
        
        # Start Running
        with self.results_lock:
            self.running_count += 1
        self.root.after(0, self.update_progress_ui)
        self.update_input_status(iid, "Đang chạy...", "running")
        
        # Get Data from map
        raw_parts = self.data_map.get(iid)
        # Mapping: User[0], Pass[1], 2FA[2], Email[3], PassEmail[4], Post[5], Follow[6], Following[7], Cookie[8]
        username = raw_parts[0]
        email = raw_parts[3]
        email_pass = raw_parts[4]
        cookie_str = raw_parts[8].strip()

        driver = None
        result_2fa = ""
        status_msg = ""
        is_success = False

        try:
            # 1. Login Logic
            # Lấy trạng thái Headless từ GUI (Thread Safe - truy cập variable cần cẩn thận hoặc lấy từ start)
            # Tuy nhiên tk.BooleanVar không thread-safe lắm nhưng đọc 1 lần thường ok.
            # Tốt nhất là pass value vào function process_one_account
            # Nhưng ở đây self.var_headless.get() trong thread con có thể lỗi ở strict mode của Tkinter.
            # -> Sửa lại: Lấy value ở hàm start_process rồi pass vào process_one_account
            # Hoặc dùng self.root.tk.call để lấy?
            # Đơn giản nhất: Do var_headless ít thay đổi khi đang chạy, ta lấy giá trị hiện tại.
            # Lưu ý: Tkinter Variable .get() chỉ nên gọi ở Main Thread.
            
            # Giải pháp: Sẽ sửa hàm start_process để lấy giá trị headless và lưu vào self.current_headless_mode
            is_headless = getattr(self, 'current_headless_mode', False)
            
            driver = get_driver(headless=is_headless)
            
            if login_instagram_via_cookie(driver, cookie_str):
                # 2. Setup 2FA Logic
                # Pass username để chọn đúng dòng nếu có nhiều tài khoản
                secret_key = setup_2fa(driver, email, email_pass, target_username=username)
                
                result_2fa = secret_key
                status_msg = "Thành công"
                is_success = True
            else:
                status_msg = "Cookie Die/Login Fail"
                result_2fa = "FAIL"
                
        except Exception as e:
            status_msg = f"Lỗi: {e}"
            # Clean msg
            status_msg = status_msg.replace("\n", " ")[:50] # Shorten
            result_2fa = "ERROR"
        finally:
            if driver:
                try: driver.quit()
                except: pass

        # Update Counters
        with self.results_lock:
            self.running_count -= 1
            self.processed_count += 1
            if is_success:
                self.success_count += 1
        self.root.after(0, self.update_progress_ui)

        # Update Input UI: Fill 2FA column (index 2) and Note (index 10)
        tag = "success" if is_success else "fail"
        self.update_input_row_result(iid, result_2fa, status_msg, tag)
        
        # Add to Output
        # self.add_output_row(iid, result_2fa, status_msg, tag)

    def update_input_status(self, iid, status_text, tag):
        def _update():
            if self.tree_input.exists(iid):
                vals = list(self.tree_input.item(iid, "values"))
                vals[10] = status_text # Note column
                self.tree_input.item(iid, values=vals, tags=(tag,))
                self.tree_input.see(iid)
        self.root.after(0, _update)

    def update_input_row_result(self, iid, fa_code, note, tag):
        def _update():
            if self.tree_input.exists(iid):
                vals = list(self.tree_input.item(iid, "values"))
                vals[3] = fa_code   # Update 2FA Column (Index 3: ID, User, Pass, 2FA)
                vals[10] = note     # Update Note
                self.tree_input.item(iid, values=vals, tags=(tag,))
        self.root.after(0, _update)

    def add_output_row(self, iid_ref, fa_code, note, tag):
        # Lấy data gốc và update kết quả để đưa sang output
        raw_parts = list(self.data_map.get(iid_ref))
        # Update part 2FA (index 2) if successful
        if fa_code and fa_code != "FAIL" and fa_code != "ERROR":
            raw_parts[2] = fa_code
            
        # Create row values
        # "ID", "User", "PASS", "2FA", "Email", "Pass Email", "Post", "Followers", "Following", "COOKIE", "Note"
        # Input 'raw_parts' length is 9 (0-8). Note is extra. ID is generated.
        
        # Lấy STT tương ứng với input. iid_ref là string index 0-based.
        # ID hiển thị = iid_ref + 1
        display_id = int(iid_ref) + 1
        
        row_vals = [
            display_id,
            raw_parts[0],
            raw_parts[1],
            raw_parts[2], # updated 2FA
            raw_parts[3],
            raw_parts[4],
            raw_parts[5],
            raw_parts[6],
            raw_parts[7],
            raw_parts[8],
            note
        ]
        
        def _add():
            self.tree_output.insert("", 0, values=row_vals, tags=(tag,))
        self.root.after(0, _add)

    def stop_process(self):
        if not self.is_running: return
        if messagebox.askyesno("Xác nhận", "Bạn có muốn dừng tiến trình?"):
            self.stop_event.set()
            with self.task_queue.mutex:
                self.task_queue.queue.clear()
            self.status_var.set("Đang dừng... Đợi các luồng hiện tại hoàn tất.")

    def on_finish(self):
        self.is_running = False
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.status_var.set("Hoàn tất / Đã dừng.")
        messagebox.showinfo("Thông báo", "Quá trình hoàn tất.")

if __name__ == "__main__":
    root = tk.Tk()
    app = Instagram2FAToolApp(root)
    root.mainloop()
