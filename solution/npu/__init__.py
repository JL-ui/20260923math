# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Sonnet 5（型号 claude-sonnet-5）、Claude Opus 5.5（型号 claude-opus-5-5）
# 开发机构：Anthropic 公司
# 版本发布日期：Claude Sonnet 5 为 2026-06-30，Claude Opus 5.5 为 2026-09-22
"""通用神经网络处理器下的多核调度问题 —— 求解工程包。

模块划分：
    paths        项目路径与官方配置
    graphlib     计算图解析、算子级 DAG、结构与代价特征
    features     图特征提取与缓存
    evaluate     官方评估器封装 + 解缓存
    partition    切图算法（问题 1/2/3 共用的构造式算法族）
    assign       核心分配与同核顺序
    localsearch  局部搜索 / 增量优化
    cachemodel   问题 3 的 L2 只读 Cache 收益模型
    algorithms   基线算法 + 主算法的统一入口
    experiment   实验驱动、结果记录
    plots        论文图表自动生成
"""

__all__ = [
    'paths', 'graphlib', 'features', 'evaluate', 'partition',
    'assign', 'localsearch', 'cachemodel', 'algorithms',
    'experiment', 'plots',
]
