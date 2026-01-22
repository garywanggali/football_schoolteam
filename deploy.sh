#!/bin/bash
# 自动部署脚本

echo "🚀 开始部署云谷足球队应用..."

# 1. 检查 Python3
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: 未找到 python3，请先安装。"
    exit 1
fi

# 2. 设置虚拟环境
VENV_DIR="venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "🛠️  正在创建虚拟环境..."
    python3 -m venv $VENV_DIR
    if [ $? -ne 0 ]; then
        echo "❌ 错误: 虚拟环境创建失败。"
        exit 1
    fi
else
    echo "✅ 虚拟环境已存在。"
fi

# 3. 激活虚拟环境并安装依赖
echo "📦 正在安装依赖..."
# 使用虚拟环境中的 pip
./$VENV_DIR/bin/python -m pip install --upgrade pip
./$VENV_DIR/bin/pip install -r requirements.txt

if [ $? -ne 0 ]; then
    echo "❌ 错误: 依赖安装失败。"
    exit 1
fi

# 4. 启动应用
# 先停止旧进程（如果存在）
echo "🔄 正在停止旧进程..."
pkill -f "python app.py" || true

echo "🌐 正在启动应用，监听端口 5200..."
# 使用虚拟环境中的 python 启动
nohup ./$VENV_DIR/bin/python app.py > app.log 2>&1 &

echo "✅ 部署完成！"
echo "应用正在虚拟环境中后台运行。"
echo "你可以通过 'tail -f app.log' 查看运行日志。"
echo "访问地址: http://110.40.153.38:5200"
