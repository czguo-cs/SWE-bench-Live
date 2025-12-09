#代理配置
export https_proxy="http://iJbVyX:mJ8eR9tU6%5Bs@10.251.112.51:8799"
export http_proxy="http://iJbVyX:mJ8eR9tU6%5Bs@10.251.112.51:8799"
export no_proxy="localhost,127.0.0.1,::1,10.0.0.0/8,192.168.0.0/16,172.16.0.0/12,*.lan,.baidu.com,.baidu-int.com,baidu.com,baidu-int.com"
export NO_PROXY="$no_proxy"
#模型环境变量配置
export OPENAI_API_KEY="sk-WRdpcxwBFvnUWaE6IUqepIBmBZE2jQCC3xAWVuhGXF4am4Fe"
export TAVILY_API_KEY='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'
python -m launch.run --config-path test-config.json