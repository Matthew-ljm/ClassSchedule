import tkinter as tk

root = tk.Tk()
root.title("Seewo Simulator")
root.geometry("480x320+100+100")
root.attributes("-topmost", True)

tk.Label(
    root,
    text="Seewo Simulator\n(easinote.exe)",
    font=("Microsoft YaHei", 20)
).pack(expand=True, fill="both")

root.mainloop()