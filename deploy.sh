#!/bin/bash
# 自动部署脚本

echo "🚀 开始部署云谷足球队应用..."

# 1. 检查 Python 环境
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: 未找到 python3，请先安装。"
    exit 1
fi

# 2. 安装依赖
echo "📦 正在安装依赖..."
python3 -m pip install -r requirements.txt

# 3. 启动应用
echo "🌐 正在启动应用，监听端口 5200..."
# 使用 nohup 后台运行，并将日志输出到 app.log
nohup python3 app.py > app.log 2>&1 &

echo "✅ 部署完成！"
echo "应用正在后台运行。你可以通过 'tail -f app.log' 查看运行日志。"
echo "访问地址: http://110.40.153.38:5200"
