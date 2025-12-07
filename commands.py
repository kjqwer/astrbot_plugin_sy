from astrbot.api.event import AstrMessageEvent
from astrbot.api import logger
from .utils import save_reminder_data, check_permission_and_return_error
from .command_utils import UnifiedCommandProcessor, ListGenerator
import functools

def check_permission(func):
    '''权限检查装饰器'''
    @functools.wraps(func)
    async def wrapper(self, event, *args, **kwargs):
        error_msg = check_permission_and_return_error(event, self.star.whitelist)
        if error_msg:
            yield event.plain_result(error_msg)
            return
        async for result in func(self, event, *args, **kwargs):
            yield result
    return wrapper


class ReminderCommands:
    def __init__(self, star_instance):
        self.star = star_instance
        self.context = star_instance.context
        self.reminder_data = star_instance.reminder_data
        self.data_file = star_instance.data_file
        self.scheduler_manager = star_instance.scheduler_manager
        self.unique_session = star_instance.unique_session
        self.tools = star_instance.tools
        # 初始化统一处理器
        self.processor = UnifiedCommandProcessor(star_instance)

    @check_permission
    async def list_reminders(self, event: AstrMessageEvent):
        '''列出所有提醒和任务'''
        # 获取用户ID，用于会话隔离
        creator_id = event.get_sender_id()
        
        # 获取会话ID
        raw_msg_origin = event.unified_msg_origin
        if self.unique_session:
            # 使用会话隔离
            msg_origin = self.tools.get_session_id(raw_msg_origin, creator_id)
        else:
            msg_origin = raw_msg_origin
            
        # 使用兼容性处理器获取提醒列表
        reminders = self.star.compatibility_handler.get_reminders(msg_origin)
        if not reminders:
            yield event.plain_result("当前没有设置任何提醒或任务。")
            return
            
        # 直接使用 ListGenerator 生成列表字符串，不再调用 LLM
        list_str = ListGenerator.generate_list_string(reminders)
        
        # 添加删除提示
        list_str += "\n\n使用 /rmd rm <序号> 删除提醒、任务或指令任务"
        
        yield event.plain_result(list_str)

    @check_permission
    async def remove_reminder(self, event: AstrMessageEvent, index: int):
        '''删除提醒、任务或指令任务
        
        Args:
            index(int): 提醒、任务或指令任务的序号
        '''
        # 获取用户ID，用于会话隔离
        creator_id = event.get_sender_id()
        
        # 获取会话ID
        raw_msg_origin = event.unified_msg_origin
        if self.unique_session:
            # 使用会话隔离
            msg_origin = self.tools.get_session_id(raw_msg_origin, creator_id)
        else:
            msg_origin = raw_msg_origin
            
        # 使用兼容性处理器获取提醒列表
        reminders = self.star.compatibility_handler.get_reminders(msg_origin)
        if not reminders:
            yield event.plain_result("没有设置任何提醒或任务。")
            return
            
        if index < 1 or index > len(reminders):
            yield event.plain_result("序号无效。")
            return
            
        # 使用兼容性处理器删除提醒
        removed_item, actual_key = self.star.compatibility_handler.remove_reminder(msg_origin, index - 1)
        if removed_item is None:
            yield event.plain_result(actual_key)  # actual_key 包含错误信息
            return
        
        # 尝试删除调度任务 - 优先使用保存的任务ID
        job_found = False
        
        # 如果有保存的任务ID，直接删除
        if removed_item.get('job_id'):
            try:
                self.scheduler_manager.remove_job(removed_item['job_id'])
                logger.info(f"Successfully removed job by stored ID: {removed_item['job_id']}")
                job_found = True
            except Exception as e:
                logger.warning(f"Failed to remove job by stored ID {removed_item['job_id']}: {str(e)}")
        
        # 如果直接删除失败，则通过内容匹配删除
        if not job_found:
            for job in self.scheduler_manager.scheduler.get_jobs():
                if job.id.startswith(f"reminder_") and len(job.args) >= 2:
                    try:
                        # 检查任务参数中的提醒内容是否匹配
                        job_session_id = job.args[0]
                        job_reminder = job.args[1]
                        if (job_session_id == actual_key and 
                            isinstance(job_reminder, dict) and
                            job_reminder.get('text') == removed_item.get('text') and
                            job_reminder.get('datetime') == removed_item.get('datetime')):
                            self.scheduler_manager.remove_job(job.id)
                            logger.info(f"Successfully removed job by content match: {job.id}")
                            job_found = True
                            break
                    except Exception as e:
                        logger.error(f"Error checking job {job.id}: {str(e)}")
        
        if not job_found:
            logger.warning(f"No matching job found for removed item: {removed_item.get('text', 'unknown')}")
            
        await save_reminder_data(self.data_file, self.reminder_data)
        
        is_command_task = removed_item.get("is_command_task", False)
        is_task = removed_item.get("is_task", False)
        
        if is_command_task:
            item_type = "指令任务"
            display_text = f"{removed_item['text']}"
        elif is_task:
            item_type = "任务"
            display_text = removed_item['text']
        else:
            item_type = "提醒"
            display_text = removed_item['text']
        
        provider = self.context.get_using_provider()
        if provider:
            prompt = f"用户删除了一个{item_type}，内容是'{display_text}'。请用自然的语言确认删除操作。直接发出对话内容，就是你说的话，不要有其他的背景描述。"
            response = await provider.text_chat(
                prompt=prompt,
                session_id=event.session_id,
                contexts=[]  # 确保contexts是一个空列表而不是None
            )
            yield event.plain_result(response.completion_text)
        else:
            yield event.plain_result(f"已删除{item_type}：{display_text}")

    @check_permission
    async def add_reminder(self, event: AstrMessageEvent, text: str, time_str: str, week: str | None = None, repeat: str | None = None, holiday_type: str | None = None):
        '''手动添加提醒
        
        Args:
            text(string): 提醒内容
            time_str(string): 时间，格式为 HH:MM 或 HHMM
            week(string): 可选，开始星期：mon,tue,wed,thu,fri,sat,sun
            repeat(string): 可选，重复类型：daily,weekly,monthly,yearly或带节假日类型的组合（如daily workday）
            holiday_type(string): 可选，节假日类型：workday(仅工作日执行)，holiday(仅法定节假日执行)
        '''
        # 使用统一处理器处理添加提醒的逻辑
        async for result in self.processor.process_add_item(
            event, 'reminder', text, time_str, week, repeat, holiday_type
        ):
            yield result

    @check_permission
    async def add_task(self, event: AstrMessageEvent, text: str, time_str: str, week: str | None = None, repeat: str | None = None, holiday_type: str | None = None):
        '''手动添加任务
        
        Args:
            text(string): 任务内容
            time_str(string): 时间，格式为 HH:MM 或 HHMM
            week(string): 可选，开始星期：mon,tue,wed,thu,fri,sat,sun
            repeat(string): 可选，重复类型：daily,weekly,monthly,yearly或带节假日类型的组合（如daily workday）
            holiday_type(string): 可选，节假日类型：workday(仅工作日执行)，holiday(仅法定节假日执行)
        '''
        # 使用统一处理器处理添加任务的逻辑
        async for result in self.processor.process_add_item(
            event, 'task', text, time_str, week, repeat, holiday_type
        ):
            yield result

    @check_permission
    async def show_help(self, event: AstrMessageEvent):
        '''显示帮助信息'''
        help_text = """提醒与任务功能指令说明：

【提醒】：到时间后会提醒你做某事
【任务】：到时间后AI会自动执行指定的操作
【指令任务】：到时间后直接执行指定的指令并转发结果

1. 添加提醒：
   /rmd add <内容> <时间> [开始星期] [重复类型] [--holiday_type=...]
   
   时间格式支持：
   - HH:MM 或 HH：MM (如 8:05)
   - HHMM (如 0805)
   - YYYYMMDDHHII (如 202509170600)
   - YYYY-MM-DD-HH:MM (如 2025-09-17-06:00)
   - MM-DD-HH:MM (如 09-17-06:00)
   - MMDDHHII (如 09170600)
   
   例如：
   - /rmd add 写周报 8:05
   - /rmd add 吃饭 8:05 sun daily (从周日开始每天)
   - /rmd add 开会 2025-09-17-08:00 (指定具体日期)
   - /rmd add 交房租 09-01-08:00 monthly (每月1号)
   - /rmd add 上班打卡 8:30 daily workday (每个工作日，法定节假日不触发)
   - /rmd add 休息提醒 9:00 daily holiday (每个法定节假日触发)

2. 添加任务：
   /rmd task <内容> <时间> [开始星期] [重复类型] [--holiday_type=...]
   
   时间格式同上，例如：
   - /rmd task 发送天气预报 8:00
   - /rmd task 汇总今日新闻 18:00 daily
   - /rmd task 推送工作安排 09-01-09:00 monthly workday (每月1号工作日推送)

2.5. 添加指令任务：
   /rmd command <指令> <时间> [开始星期] [重复类型] [--holiday_type=...]
   例如：
   - /rmd command /memory_config 8:00
   - /rmd command /weather 9:00 daily
   - /rmd command /news 18:00 mon weekly (每周一推送)
   - /rmd command /rmd--ls 8:00 daily (使用--避免指令被错误分割)
   - /rmd command /rmd--ls----before--每日提醒 8:00 daily (自定义标识放在开头)
   - /rmd command /rmd--ls----after--执行完成 8:00 daily (自定义标识放在末尾)

3. 查看提醒和任务：
   /rmd ls - 列出所有提醒和任务

4. 删除提醒或任务：
   /rmd rm <序号> - 删除指定提醒或任务，注意任务序号是提醒序号继承，比如提醒有两个，任务1的序号就是3（llm会自动重编号）

5. 星期可选值：
   - mon: 周一
   - tue: 周二
   - wed: 周三
   - thu: 周四
   - fri: 周五
   - sat: 周六
   - sun: 周日

6. 重复类型：
   - daily: 每天重复
   - weekly: 每周重复
   - monthly: 每月重复
   - yearly: 每年重复

7. 节假日类型：
   - workday: 仅工作日触发（法定节假日不触发）
   - holiday: 仅法定节假日触发

8. AI智能提醒与任务
   正常对话即可，AI会自己设置提醒或任务，但需要AI支持LLM

9. 会话隔离功能
   {session_isolation_status}
   - 关闭状态：群聊中所有成员共享同一组提醒和任务
   - 开启状态：群聊中每个成员都有自己独立的提醒和任务
   
   可以通过管理面板的插件配置开启或关闭此功能

注：时间格式为 HH:MM 或 HHMM，如 8:05 或 0805

10. 数量限制
   每个用户最多可创建 {max_reminders} 个提醒和任务
   {limit_scope_description}

指令任务自定义标识说明：
- 使用 ---- 分隔符可以自定义指令任务的标识文字
- 格式：指令----位置--自定义文字
- 位置可选：before(开头)、after(末尾)、start(开头)、end(末尾)
- 示例：/rmd--ls----before--每日提醒 或 /rmd--ls----after--执行完成
- 如果不使用 ---- 分隔符，默认显示 [指令任务]

法定节假日数据来源：http://timor.tech/api/holiday""".format(
           session_isolation_status="当前已开启会话隔离" if self.unique_session else "当前未开启会话隔离",
           max_reminders=self.star.max_reminders_per_user if self.star.max_reminders_per_user > 0 else "无限制",
           limit_scope_description="- 会话隔离开启：每个用户在每个群聊中独立计算" if self.unique_session else "- 会话隔离关闭：全局共享限制（所有用户共用）"
        )
        yield event.plain_result(help_text)

    @check_permission
    async def add_command_task(self, event: AstrMessageEvent, command: str, time_str: str, week: str | None = None, repeat: str | None = None, holiday_type: str | None = None):
        '''设置指令任务
        
        Args:
            command(string): 要执行的指令，如"/memory_config"或"/rmd--ls"（多个指令用--分隔）
            time_str(string): 时间，格式为 HH:MM 或 HHMM
            week(string): 可选，开始星期：mon,tue,wed,thu,fri,sat,sun
            repeat(string): 可选，重复类型：daily,weekly,monthly,yearly
            holiday_type(string): 可选，节假日类型：workday(仅工作日执行)，holiday(仅法定节假日执行)
        '''
        # 使用统一处理器处理添加指令任务的逻辑
        async for result in self.processor.process_add_item(
            event, 'command_task', command, time_str, week, repeat, holiday_type
        ):
            yield result



    @check_permission
    async def add_remote_reminder(self, event: AstrMessageEvent, group_id: str, text: str, time_str: str, week: str | None = None, repeat: str | None = None, holiday_type: str | None = None):
        '''在指定群聊中手动添加提醒'''
        async for result in self.processor.process_add_item(
            event, 'reminder', text, time_str, week, repeat, holiday_type, group_id
        ):
            yield result

    @check_permission
    async def add_remote_task(self, event: AstrMessageEvent, group_id: str, text: str, time_str: str, week: str | None = None, repeat: str | None = None, holiday_type: str | None = None):
        '''在指定群聊中手动添加任务'''
        async for result in self.processor.process_add_item(
            event, 'task', text, time_str, week, repeat, holiday_type, group_id
        ):
            yield result

    @check_permission
    async def add_remote_command_task(self, event: AstrMessageEvent, group_id: str, command: str, time_str: str, week: str | None = None, repeat: str | None = None, holiday_type: str | None = None):
        '''在指定群聊中设置指令任务'''
        async for result in self.processor.process_add_item(
            event, 'command_task', command, time_str, week, repeat, holiday_type, group_id
        ):
            yield result

    @check_permission
    async def show_remote_help(self, event: AstrMessageEvent):
        '''显示远程群聊帮助信息'''
        help_text = """远程群聊提醒与任务功能指令说明：

【功能】：在指定的群聊中设置、查看和管理提醒、任务或指令任务

1. 在指定群聊中添加提醒：
   /rmdg add <群聊ID> <内容> <时间> [开始星期] [重复类型] [--holiday_type=...]
   例如：
   - /rmdg add 1001914995 写周报 8:05
   - /rmdg add 1001914995 吃饭 8:05 sun daily (从周日开始每天)
   - /rmdg add 1001914995 开会 8:05 mon weekly (每周一)
   - /rmdg add 1001914995 交房租 8:05 fri monthly (从周五开始每月)
   - /rmdg add 1001914995 上班打卡 8:30 daily workday (每个工作日，法定节假日不触发)

2. 在指定群聊中添加任务：
   /rmdg task <群聊ID> <内容> <时间> [开始星期] [重复类型] [--holiday_type=...]
   例如：
   - /rmdg task 1001914995 发送天气预报 8:00
   - /rmdg task 1001914995 汇总今日新闻 18:00 daily
   - /rmdg task 1001914995 推送工作安排 9:00 mon weekly workday (每周一工作日推送)

3. 在指定群聊中添加指令任务：
   /rmdg command <群聊ID> <指令> <时间> [开始星期] [重复类型] [--holiday_type=...]
   例如：
   - /rmdg command 1001914995 /memory_config 8:00
   - /rmdg command 1001914995 /weather 9:00 daily
   - /rmdg command 1001914995 /news 18:00 mon weekly (每周一推送)
   - /rmdg command 1001914995 /rmd--ls----before--每日提醒 8:00 daily (自定义标识放在开头)
   - /rmdg command 1001914995 /rmd--ls----after--执行完成 8:00 daily (自定义标识放在末尾)

4. 查看指定群聊的提醒和任务：
   /rmdg ls <群聊ID>
   例如：
   - /rmdg ls 1001914995

5. 删除指定群聊中的提醒或任务：
   /rmdg rm <群聊ID> <序号>
   例如：
   - /rmdg rm 1001914995 1 (删除序号为1的提醒或任务)

6. 群聊ID获取方法：
   - QQ群：群号，如 1001914995
   - 微信群：群聊的wxid，如 wxid_hbjtu1j2gf5x22
   - 其他平台：对应的群聊标识符

7. 星期可选值：
   - mon: 周一
   - tue: 周二
   - wed: 周三
   - thu: 周四
   - fri: 周五
   - sat: 周六
   - sun: 周日

8. 重复类型：
   - daily: 每天重复
   - weekly: 每周重复
   - monthly: 每月重复
   - yearly: 每年重复

9. 节假日类型：
   - workday: 仅工作日触发（法定节假日不触发）
   - holiday: 仅法定节假日触发

10. 数量限制
   每个用户最多可创建 {} 个提醒和任务
   {}

注：时间格式为 HH:MM 或 HHMM，如 8:05 或 0805

指令任务自定义标识说明：
- 使用 ---- 分隔符可以自定义指令任务的标识文字
- 格式：指令----位置--自定义文字
- 位置可选：before(开头)、after(末尾)、start(开头)、end(末尾)
- 示例：/rmd--ls----before--每日提醒 或 /rmd--ls----after--执行完成
- 如果不使用 ---- 分隔符，默认显示 [指令任务]

法定节假日数据来源：http://timor.tech/api/holiday""".format(
            self.star.max_reminders_per_user if self.star.max_reminders_per_user > 0 else "无限制",
            "- 会话隔离开启：每个用户在每个群聊中独立计算" if self.unique_session else "- 会话隔离关闭：全局共享限制（所有用户共用）"
        )
        yield event.plain_result(help_text)

    @check_permission
    async def list_remote_reminders(self, event: AstrMessageEvent, group_id: str):
        '''列出指定群聊中的所有提醒和任务
        
        Args:
            group_id(string): 群聊ID
        '''
        # 获取用户ID，用于会话隔离
        creator_id = event.get_sender_id()
        
        # 获取平台ID（用户自定义的平台标识符）
        platform_id = event.get_platform_id()
        
        # 构建远程群聊的会话ID
        if self.unique_session:
            # 使用会话隔离
            msg_origin = f"{platform_id}:GroupMessage:{group_id}_{creator_id}"
        else:
            msg_origin = f"{platform_id}:GroupMessage:{group_id}"
            
        # 使用兼容性处理器获取提醒列表
        reminders = self.star.compatibility_handler.get_reminders(msg_origin)
        if not reminders:
            yield event.plain_result(f"群聊 {group_id} 中没有设置任何提醒或任务。")
            return
            
        # 直接使用 ListGenerator 生成列表字符串，不再调用 LLM
        list_str = ListGenerator.generate_list_string(reminders)
        
        # 添加删除提示
        list_str += f"\n\n使用 /rmdg rm {group_id} <序号> 删除提醒、任务或指令任务"
        
        yield event.plain_result(list_str)

    @check_permission
    async def remove_remote_reminder(self, event: AstrMessageEvent, group_id: str, index: int):
        '''删除指定群聊中的提醒、任务或指令任务
        
        Args:
            group_id(string): 群聊ID
            index(int): 提醒、任务或指令任务的序号
        '''
        # 获取用户ID，用于会话隔离
        creator_id = event.get_sender_id()
        
        # 获取平台ID（用户自定义的平台标识符）
        platform_id = event.get_platform_id()
        
        # 构建远程群聊的会话ID
        if self.unique_session:
            # 使用会话隔离
            msg_origin = f"{platform_id}:GroupMessage:{group_id}_{creator_id}"
        else:
            msg_origin = f"{platform_id}:GroupMessage:{group_id}"
            
        # 使用兼容性处理器删除提醒
        removed_item, actual_key = self.star.compatibility_handler.remove_reminder(msg_origin, index - 1)
        if removed_item is None:
            yield event.plain_result(actual_key)  # actual_key 包含错误信息
            return
            
        # 尝试删除调度任务 - 优先使用保存的任务ID
        job_found = False
        
        # 如果有保存的任务ID，直接删除
        if removed_item.get('job_id'):
            try:
                self.scheduler_manager.remove_job(removed_item['job_id'])
                logger.info(f"Successfully removed job by stored ID: {removed_item['job_id']}")
                job_found = True
            except Exception as e:
                logger.warning(f"Failed to remove job by stored ID {removed_item['job_id']}: {str(e)}")
        
        # 如果直接删除失败，则通过内容匹配删除
        if not job_found:
            for job in self.scheduler_manager.scheduler.get_jobs():
                if job.id.startswith(f"reminder_") and len(job.args) >= 2:
                    try:
                        # 检查任务参数中的提醒内容是否匹配
                        job_session_id = job.args[0]
                        job_reminder = job.args[1]
                        if (job_session_id == actual_key and 
                            isinstance(job_reminder, dict) and
                            job_reminder.get('text') == removed_item.get('text') and
                            job_reminder.get('datetime') == removed_item.get('datetime')):
                            self.scheduler_manager.remove_job(job.id)
                            logger.info(f"Successfully removed job by content match: {job.id}")
                            job_found = True
                            break
                    except Exception as e:
                        logger.error(f"Error checking job {job.id}: {str(e)}")
        
        if not job_found:
            logger.warning(f"No matching job found for removed item: {removed_item.get('text', 'unknown')}")
        await save_reminder_data(self.data_file, self.reminder_data)
        
        is_command_task = removed_item.get("is_command_task", False)
        is_task = removed_item.get("is_task", False)
        
        if is_command_task:
            item_type = "指令任务"
            display_text = f"/{removed_item['text']}"
        elif is_task:
            item_type = "任务"
            display_text = removed_item['text']
        else:
            item_type = "提醒"
            display_text = removed_item['text']
        
        provider = self.context.get_using_provider()
        if provider:
            prompt = f"用户删除了群聊 {group_id} 中的一个{item_type}，内容是'{display_text}'。请用自然的语言确认删除操作。直接发出对话内容，就是你说的话，不要有其他的背景描述。"
            response = await provider.text_chat(
                prompt=prompt,
                session_id=event.session_id,
                contexts=[]  # 确保contexts是一个空列表而不是None
            )
            yield event.plain_result(response.completion_text)
        else:
            yield event.plain_result(f"已删除群聊 {group_id} 中的{item_type}：{display_text}")