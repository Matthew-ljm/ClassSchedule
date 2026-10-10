import tkinter as tk

root = tk.Tk()
root.title("WPS Presentation Slide Show")  # 也可以用 "幻灯片放映"
root.attributes("-fullscreen", True)
root.attributes("-topmost", True)
root.configure(bg="black")

tk.Label(
    root,
    text="WPS Slide Show Simulator",
    fg="white",
    bg="black",
    font=("Microsoft YaHei", 28)
).pack(expand=True)

# 按 Esc 退出
root.bind("<Escape>", lambda e: root.destroy())

root.mainloop()