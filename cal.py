import tkinter as tk
from tkinter import ttk

class Calculator:
    def __init__(self, root):
        self.root = root
        self.root.title("Simple Calculator")
        self.root.geometry("400x500")
        self.root.resizable(False, False)
        
        # Variables
        self.current_input = ""
        self.result_var = tk.StringVar()
        self.result_var.set("0")
        
        # Create GUI elements
        self.create_display()
        self.create_buttons()
        
    def create_display(self):
        # Display frame
        display_frame = ttk.Frame(self.root, padding="10")
        display_frame.grid(row=0, column=0, columnspan=4, sticky="ew")
        
        # Entry widget for display
        self.display = ttk.Entry(
            display_frame, 
            textvariable=self.result_var, 
            font=('Arial', 24), 
            justify='right',
            state='readonly'
        )
        self.display.pack(fill="both", expand=True)
        
    def create_buttons(self):
        # Button layout
        buttons = [
            ('7', 1, 0), ('8', 1, 1), ('9', 1, 2), ('/', 1, 3),
            ('4', 2, 0), ('5', 2, 1), ('6', 2, 2), ('*', 2, 3),
            ('1', 3, 0), ('2', 3, 1), ('3', 3, 2), ('-', 3, 3),
            ('C', 4, 0), ('0', 4, 1), ('=', 4, 2), ('+', 4, 3)
        ]
        
        # Create buttons
        for (text, row, col) in buttons:
            button = ttk.Button(
                self.root,
                text=text,
                command=lambda t=text: self.on_button_click(t)
            )
            button.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
            
        # Configure grid weights for resizing
        for i in range(5):
            self.root.grid_rowconfigure(i, weight=1)
        for i in range(4):
            self.root.grid_columnconfigure(i, weight=1)
    
    def on_button_click(self, button_text):
        if button_text == 'C':
            # Clear
            self.current_input = ""
            self.result_var.set("0")
        elif button_text == '=':
            # Calculate result
            try:
                result = eval(self.current_input)
                self.result_var.set(str(result))
                self.current_input = str(result)
            except:
                self.result_var.set("Error")
                self.current_input = ""
        else:
            # Add to current input
            if self.result_var.get() == "0" and button_text not in '/*-+':
                self.current_input = button_text
            else:
                self.current_input += button_text
            self.result_var.set(self.current_input)

def main():
    root = tk.Tk()
    calculator = Calculator(root)
    root.mainloop()

if __name__ == "__main__":
    main()