import gradio as gr

def greet(name):
    return "Hello " + name + "!"

print("创建Gradio界面...")
demo = gr.Interface(fn=greet, inputs="text", outputs="text")
print("启动Gradio服务器...")
demo.launch(server_name="127.0.0.1", server_port=7860, share=False, inbrowser=True)