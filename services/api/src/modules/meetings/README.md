# 会议模块

会议纪要生成改为 RabbitMQ + Celery 队列，API 内不再执行生成循环。启动方式与可靠性见 [异步任务说明](../../infrastructure/tasks/README.md)。PG 保存生成输入快照、状态和结果；完成/失败通过 WebSocket 通知前端 Toast。
