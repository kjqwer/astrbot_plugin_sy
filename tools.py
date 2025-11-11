import datetime
from typing import Union
from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import Context
from astrbot.api import logger
from .utils import parse_datetime_for_llm, save_reminder_data, check_reminder_limit

class ReminderTools:
    def __init__(self, star_instance):
        self.star = star_instance
        self.context = star_instance.context
        self.reminder_data = star_instance.reminder_data
        self.data_file = star_instance.data_file
        self.scheduler_manager = star_instance.scheduler_manager
        self.unique_session = star_instance.unique_session
        # 延迟初始化统一处理器，避免循环依赖
        self._processor = None
    
    @property
    def processor(self):
        """懒加载统一处理器实例"""
        if self._processor is None:
            from .command_utils import UnifiedCommandProcessor
            self._processor = UnifiedCommandProcessor(self.star)
        return self._processor
    
    def get_session_id(self, msg_origin, creator_id=None):
        """
        根据会话隔离设置，获取正确的会话ID
        
        Args:
            msg_origin: 原始会话ID
            creator_id: 创建者ID
            
        Returns:
            str: 处理后的会话ID
        """
        if not self.unique_session:
            return msg_origin
            
        # 如果启用了会话隔离，并且有创建者ID，则在会话ID中添加用户标识
        if creator_id and ":" in msg_origin:
            # 在群聊环境中添加用户ID
            if (":GroupMessage:" in msg_origin or 
                "@chatroom" in msg_origin or
                ":ChannelMessage:" in msg_origin):
                # 分割会话ID并在末尾添加用户标识
                parts = msg_origin.rsplit(":", 1)
                if len(parts) == 2:
                    return f"{parts[0]}:{parts[1]}_{creator_id}"
        
        return msg_origin
    
    async def set_reminder(self, event: Union[AstrMessageEvent, Context], text: str, datetime_str: str, user_name: str = "用户", repeat: str | None = None, holiday_type: str | None = None, group_id: str | None = None):
        '''设置一个提醒
        
        Args:
            text(string): 提醒内容
            datetime_str(string): 提醒时间，格式为 %Y-%m-%d %H:%M
            user_name(string): 提醒对象名称，默认为"用户"
            repeat(string): 重复类型，可选值：daily(每天)，weekly(每周)，monthly(每月)，yearly(每年)，none(不重复)
            holiday_type(string): 可选，节假日类型：workday(仅工作日执行)，holiday(仅法定节假日执行)
            group_id(string): 可选，指定群聊ID，用于在特定群聊中设置提醒
        '''
        # 权限检查
        if hasattr(event, 'get_sender_id'):
            from .utils import check_permission_and_return_error
            error_msg = check_permission_and_return_error(event, self.star.whitelist)
            if error_msg:
                return error_msg
        
        try:
            logger.info(f"set_reminder被调用: text='{text}', datetime_str='{datetime_str}', user_name='{user_name}', repeat='{repeat}', holiday_type='{holiday_type}', group_id='{group_id}'")
            
            # 如果是Context类型，无法使用统一处理器，使用原有逻辑
            if isinstance(event, Context):
                logger.info("使用Context模式的legacy方法")
                return await self._legacy_set_reminder(event, text, datetime_str, user_name, repeat, holiday_type)
            
            # 为LLM工具使用简单的时间解析
            try:
                parsed_datetime_str = parse_datetime_for_llm(datetime_str)
                logger.info(f"时间解析成功: '{datetime_str}' -> '{parsed_datetime_str}'")
            except ValueError as e:
                logger.error(f"时间解析失败: {e}")
                return str(e)
            
            # 使用统一处理器处理提醒
            logger.info("开始调用统一处理器")
            result_message = None
            async for result in self.processor.process_add_item(
                event, 'reminder', text, parsed_datetime_str, None, repeat, holiday_type, group_id, time_already_parsed=True, user_name=user_name
            ):
                logger.info(f"收到统一处理器结果: {type(result)}")
                # event.plain_result() 返回的是MessageEventResult对象
                # 使用get_plain_text()方法提取纯文本消息
                if hasattr(result, 'get_plain_text'):
                    result_message = result.get_plain_text()
                    logger.info(f"提取的消息 (get_plain_text): '{result_message}'")
                elif hasattr(result, 'chain') and result.chain:
                    # 手动提取链中的文本
                    from astrbot.core.message.components import Plain
                    texts = [comp.text for comp in result.chain if isinstance(comp, Plain)]
                    result_message = " ".join(texts)
                    logger.info(f"提取的消息 (chain): '{result_message}'")
                else:
                    result_message = str(result)
                    logger.info(f"提取的消息 (str): '{result_message}'")
                break  # 只获取第一个结果
            
            logger.info(f"最终返回消息: '{result_message}'")
            return result_message or "设置提醒成功"
                    
        except Exception as e:
            return f"设置提醒时出错：{str(e)}"
    
    async def set_task(self, event: Union[AstrMessageEvent, Context], text: str, datetime_str: str, repeat: str | None = None, holiday_type: str | None = None, group_id: str | None = None, user_name: str | None = None):
        '''设置一个任务，到时间后会让AI执行该任务
        
        Args:
            text(string): 任务内容，AI将执行的操作
            datetime_str(string): 任务执行时间，格式为 %Y-%m-%d %H:%M
            repeat(string): 重复类型，可选值：daily(每天)，weekly(每周)，monthly(每月)，yearly(每年)，none(不重复)
            holiday_type(string): 可选，节假日类型：workday(仅工作日执行)，holiday(仅法定节假日执行)
            group_id(string): 可选，指定群聊ID，用于在特定群聊中设置任务
        '''
        # 权限检查
        if hasattr(event, 'get_sender_id'):
            from .utils import check_permission_and_return_error
            error_msg = check_permission_and_return_error(event, self.star.whitelist)
            if error_msg:
                return error_msg
        
        try:
            # 如果是Context类型，无法使用统一处理器，使用原有逻辑
            if isinstance(event, Context):
                return await self._legacy_set_task(event, text, datetime_str, repeat, holiday_type)
            
            # 为LLM工具使用简单的时间解析
            try:
                parsed_datetime_str = parse_datetime_for_llm(datetime_str)
            except ValueError as e:
                return str(e)
            
            # 使用统一处理器处理任务
            result_message = None
            async for result in self.processor.process_add_item(
                event, 'task', text, parsed_datetime_str, None, repeat, holiday_type, group_id, time_already_parsed=True, user_name=user_name
            ):
                # event.plain_result() 返回的是MessageEventResult对象
                # 使用get_plain_text()方法提取纯文本消息
                if hasattr(result, 'get_plain_text'):
                    result_message = result.get_plain_text()
                elif hasattr(result, 'chain') and result.chain:
                    # 手动提取链中的文本
                    from astrbot.core.message.components import Plain
                    texts = [comp.text for comp in result.chain if isinstance(comp, Plain)]
                    result_message = " ".join(texts)
                else:
                    result_message = str(result)
                break  # 只获取第一个结果
            
            return result_message or "设置任务成功"
                    
        except Exception as e:
            return f"设置任务时出错：{str(e)}"
    
    async def _legacy_set_reminder(self, event: Context, text: str, datetime_str: str, user_name: str = "用户", repeat: str | None = None, holiday_type: str | None = None):
        '''兼容Context模式的设置提醒方法（原有逻辑）'''
        try:
            msg_origin = self.context.get_event_queue()._queue[0].session_id
            creator_id = None  # Context 模式下无法获取创建者ID
            creator_name = None
            
            # 使用兼容性处理器确保key存在
            actual_key = self.star.compatibility_handler.ensure_key_exists(msg_origin)
            
            # 检查提醒数量限制
            can_create, error_msg = check_reminder_limit(
                self.reminder_data, 
                actual_key, 
                self.star.max_reminders_per_user, 
                self.unique_session, 
                creator_id
            )
            if not can_create:
                return error_msg
            
            # 处理重复类型和节假日类型的组合
            final_repeat = repeat or "none"
            if repeat and holiday_type:
                final_repeat = f"{repeat}_{holiday_type}"
            
            reminder = {
                "text": text,
                "datetime": datetime_str,
                "user_name": user_name,
                "repeat": final_repeat,
                "creator_id": creator_id,
                "creator_name": creator_name,  # 添加创建者昵称
                "is_task": False  # 标记为提醒，不是任务
            }
            
            self.reminder_data[actual_key].append(reminder)
            
            # 解析时间
            dt = datetime.datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
            
            # 设置定时任务并保存任务ID
            job_id = self.scheduler_manager.add_job(actual_key, reminder, dt)
            reminder["job_id"] = job_id  # 保存任务ID到提醒数据中
            
            await save_reminder_data(self.data_file, self.reminder_data)
            
            # 构建提示信息
            repeat_str = ""
            if repeat == "daily" and not holiday_type:
                repeat_str = "，每天重复"
            elif repeat == "daily" and holiday_type == "workday":
                repeat_str = "，每个工作日重复（法定节假日不触发）"
            elif repeat == "daily" and holiday_type == "holiday":
                repeat_str = "，每个法定节假日重复"
            elif repeat == "weekly" and not holiday_type:
                repeat_str = "，每周重复"
            elif repeat == "weekly" and holiday_type == "workday":
                repeat_str = "，每周的这一天重复，但仅工作日触发"
            elif repeat == "weekly" and holiday_type == "holiday":
                repeat_str = "，每周的这一天重复，但仅法定节假日触发"
            elif repeat == "monthly" and not holiday_type:
                repeat_str = "，每月重复"
            elif repeat == "monthly" and holiday_type == "workday":
                repeat_str = "，每月的这一天重复，但仅工作日触发"
            elif repeat == "monthly" and holiday_type == "holiday":
                repeat_str = "，每月的这一天重复，但仅法定节假日触发"
            elif repeat == "yearly" and not holiday_type:
                repeat_str = "，每年重复"
            elif repeat == "yearly" and holiday_type == "workday":
                repeat_str = "，每年的这一天重复，但仅工作日触发"
            elif repeat == "yearly" and holiday_type == "holiday":
                repeat_str = "，每年的这一天重复，但仅法定节假日触发"
            
            return f"已设置提醒:\n内容: {text}\n时间: {datetime_str}{repeat_str}\n\n使用 /rmd ls 查看所有提醒"
            
        except Exception as e:
            return f"设置提醒时出错：{str(e)}"

    async def _legacy_set_task(self, event: Context, text: str, datetime_str: str, repeat: str | None = None, holiday_type: str | None = None):
        '''兼容Context模式的设置任务方法（原有逻辑）'''
        try:
            msg_origin = self.context.get_event_queue()._queue[0].session_id
            creator_id = None  # Context 模式下无法获取创建者ID
            creator_name = None
            
            # 使用兼容性处理器确保key存在
            actual_key = self.star.compatibility_handler.ensure_key_exists(msg_origin)
            
            # 检查提醒数量限制
            can_create, error_msg = check_reminder_limit(
                self.reminder_data, 
                actual_key, 
                self.star.max_reminders_per_user, 
                self.unique_session, 
                creator_id
            )
            if not can_create:
                return error_msg
            
            # 处理重复类型和节假日类型的组合
            final_repeat = repeat or "none"
            if repeat and holiday_type:
                final_repeat = f"{repeat}_{holiday_type}"
            
            task = {
                "text": text,
                "datetime": datetime_str,
                "user_name": "用户",  # 任务模式下不需要特别指定用户名
                "repeat": final_repeat,
                "creator_id": creator_id,
                "creator_name": creator_name,  # 添加创建者昵称
                "is_task": True  # 标记为任务，不是提醒
            }
            
            self.reminder_data[actual_key].append(task)
            
            # 解析时间
            dt = datetime.datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
            
            # 设置定时任务并保存任务ID
            job_id = self.scheduler_manager.add_job(actual_key, task, dt)
            task["job_id"] = job_id  # 保存任务ID到任务数据中
            
            await save_reminder_data(self.data_file, self.reminder_data)
            
            # 构建提示信息
            repeat_str = ""
            if repeat == "daily" and not holiday_type:
                repeat_str = "，每天重复"
            elif repeat == "daily" and holiday_type == "workday":
                repeat_str = "，每个工作日重复（法定节假日不触发）"
            elif repeat == "daily" and holiday_type == "holiday":
                repeat_str = "，每个法定节假日重复"
            elif repeat == "weekly" and not holiday_type:
                repeat_str = "，每周重复"
            elif repeat == "weekly" and holiday_type == "workday":
                repeat_str = "，每周的这一天重复，但仅工作日触发"
            elif repeat == "weekly" and holiday_type == "holiday":
                repeat_str = "，每周的这一天重复，但仅法定节假日触发"
            elif repeat == "monthly" and not holiday_type:
                repeat_str = "，每月重复"
            elif repeat == "monthly" and holiday_type == "workday":
                repeat_str = "，每月的这一天重复，但仅工作日触发"
            elif repeat == "monthly" and holiday_type == "holiday":
                repeat_str = "，每月的这一天重复，但仅法定节假日触发"
            elif repeat == "yearly" and not holiday_type:
                repeat_str = "，每年重复"
            elif repeat == "yearly" and holiday_type == "workday":
                repeat_str = "，每年的这一天重复，但仅工作日触发"
            elif repeat == "yearly" and holiday_type == "holiday":
                repeat_str = "，每年的这一天重复，但仅法定节假日触发"
            
            return f"已设置任务:\n内容: {text}\n时间: {datetime_str}{repeat_str}\n\n使用 /rmd ls 查看所有任务"
            
        except Exception as e:
            return f"设置任务时出错：{str(e)}"
    
    async def delete_reminder(self, event: Union[AstrMessageEvent, Context],
                            content: str | None = None,           # 任务内容关键词
                            time: str | None = None,              # 具体时间点 HH:MM
                            weekday: str | None = None,           # 星期 mon,tue,wed,thu,fri,sat,sun
                            repeat_type: str | None = None,       # 重复类型 daily,weekly,monthly,yearly
                            date: str | None = None,              # 具体日期 YYYY-MM-DD
                            all: str | None = None,               # 是否删除所有 "yes"/"no"
                            task_only: str = "no",       # 是否只删除任务
                            reminder_only: str = "no",    # 是否只删除提醒
                            group_id: str | None = None          # 可选，指定群聊ID
                            ):
        '''删除符合条件的提醒或者任务，可组合多个条件进行精确筛选
        
        Args:
            content(string): 可选，提醒或者任务内容包含的关键词
            time(string): 可选，具体时间点，格式为 HH:MM，如 "08:00"
            weekday(string): 可选，星期几，可选值：mon,tue,wed,thu,fri,sat,sun
            repeat_type(string): 可选，重复类型，可选值：daily,weekly,monthly,yearly
            date(string): 可选，具体日期，格式为 YYYY-MM-DD，如 "2024-02-09"
            all(string): 可选，是否删除所有提醒，可选值：yes/no，默认no
            task_only(string): 可选，是否只删除任务，可选值：yes/no，默认no
            reminder_only(string): 可选，是否只删除提醒，可选值：yes/no，默认no
            group_id(string): 可选，指定群聊ID，用于删除特定群聊中的提醒或任务
        '''
        # 权限检查
        if hasattr(event, 'get_sender_id'):
            from .utils import check_permission_and_return_error
            error_msg = check_permission_and_return_error(event, self.star.whitelist)
            if error_msg:
                return error_msg
        
        try:
            if isinstance(event, Context):
                msg_origin = self.context.get_event_queue()._queue[0].session_id
                creator_id = None
            else:
                creator_id = event.get_sender_id()
                
                if group_id:
                    # 远程群聊操作 - 构建远程会话ID
                    from .command_utils import SessionHelper
                    msg_origin = SessionHelper.build_remote_session_id(event, group_id, self.unique_session)
                else:
                    # 本地操作
                    raw_msg_origin = event.unified_msg_origin
                    # 使用会话隔离功能获取会话ID
                    msg_origin = self.get_session_id(raw_msg_origin, creator_id)
            
            # 调试信息：打印所有调度任务
            logger.info("Current jobs in scheduler:")
            for job in self.scheduler_manager.scheduler.get_jobs():
                logger.info(f"Job ID: {job.id}, Next run: {job.next_run_time}, Args: {job.args}")
            
            # 使用兼容性处理器获取提醒列表
            reminders = self.star.compatibility_handler.get_reminders(msg_origin)
            actual_key = self.star.compatibility_handler.get_actual_key(msg_origin)
            if not reminders:
                location_desc = f"群聊 {group_id} 中" if group_id else ""
                return f"当前{location_desc}没有任何提醒或任务。"
            
            # 用于存储要删除的任务索引
            to_delete = []
            
            # 验证星期格式
            week_map = {
                'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 
                'fri': 4, 'sat': 5, 'sun': 6
            }
            if weekday and weekday.lower() not in week_map:
                return "星期格式错误，可选值：mon,tue,wed,thu,fri,sat,sun"
            
            # 验证重复类型
            repeat_types = ["daily", "weekly", "monthly", "yearly"]
            if repeat_type and repeat_type.lower() not in repeat_types:
                return "重复类型错误，可选值：daily,weekly,monthly,yearly"
            
            for i, reminder in enumerate(reminders):
                dt = datetime.datetime.strptime(reminder["datetime"], "%Y-%m-%d %H:%M")
                
                # 检查是否只删除任务或只删除提醒
                is_task_only = task_only and task_only.lower() == "yes"
                is_reminder_only = reminder_only and reminder_only.lower() == "yes"
                
                if is_task_only and not reminder.get("is_task", False):
                    continue
                if is_reminder_only and reminder.get("is_task", False):
                    continue
                
                # 如果指定删除所有，直接添加
                if all and all.lower() == "yes":
                    to_delete.append(i)
                    continue
                
                # 检查各个条件，所有指定的条件都必须满足
                match = True
                
                # 检查内容
                if content and content not in reminder["text"]:
                    match = False
                
                # 检查时间点
                if time:
                    reminder_time = dt.strftime("%H:%M")
                    if reminder_time != time:
                        match = False
                
                # 检查星期
                if weekday:
                    if reminder.get("repeat") == "weekly":
                        # 对于每周重复的任务，检查是否在指定星期执行
                        if dt.weekday() != week_map[weekday.lower()]:
                            match = False
                    else:
                        # 对于非每周重复的任务，检查日期是否落在指定星期
                        if dt.weekday() != week_map[weekday.lower()]:
                            match = False
                
                # 检查重复类型
                if repeat_type and reminder.get("repeat") != repeat_type.lower():
                    match = False
                
                # 检查具体日期
                if date:
                    reminder_date = dt.strftime("%Y-%m-%d")
                    if reminder_date != date:
                        match = False
                
                # 如果所有条件都满足，添加到删除列表
                if match:
                    to_delete.append(i)
            
            if not to_delete:
                conditions = []
                if content:
                    conditions.append(f"内容包含{content}")
                if time:
                    conditions.append(f"时间为{time}")
                if weekday:
                    conditions.append(f"在{weekday}")
                if repeat_type:
                    conditions.append(f"重复类型为{repeat_type}")
                if date:
                    conditions.append(f"日期为{date}")
                if task_only:
                    conditions.append("仅任务")
                if reminder_only:
                    conditions.append("仅提醒")
                
                location_desc = f"群聊 {group_id} 中" if group_id else ""
                return f"没有在{location_desc}找到符合条件的提醒或任务：{', '.join(conditions)}"
            
            # 从后往前删除，避免索引变化
            deleted_reminders = []
            for i in sorted(to_delete, reverse=True):
                reminder = reminders[i]
                
                # 调试信息：打印正在删除的任务
                logger.info(f"Attempting to delete {'task' if reminder.get('is_task', False) else 'reminder'}: {reminder}")
                
                # 尝试删除调度任务 - 优先使用保存的任务ID
                job_found = False
                
                # 如果有保存的任务ID，直接删除
                if reminder.get('job_id'):
                    try:
                        self.scheduler_manager.remove_job(reminder['job_id'])
                        logger.info(f"Successfully removed job by stored ID: {reminder['job_id']}")
                        job_found = True
                    except Exception as e:
                        logger.warning(f"Failed to remove job by stored ID {reminder['job_id']}: {str(e)}")
                
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
                                    job_reminder.get('text') == reminder['text'] and
                                    job_reminder.get('datetime') == reminder['datetime']):
                                    self.scheduler_manager.remove_job(job.id)
                                    logger.info(f"Successfully removed job by content match: {job.id}")
                                    job_found = True
                                    break
                            except Exception as e:
                                logger.error(f"Error checking job {job.id}: {str(e)}")
                
                if not job_found:
                    logger.warning(f"No matching job found for removed item: {reminder.get('text', 'unknown')}")
                
                deleted_reminders.append(reminder)
                reminders.pop(i)
            
            # 更新数据
            self.reminder_data[actual_key] = reminders
            await save_reminder_data(self.data_file, self.reminder_data)
            
            # 调试信息：打印剩余的调度任务
            logger.info("Remaining jobs in scheduler:")
            for job in self.scheduler_manager.scheduler.get_jobs():
                logger.info(f"Job ID: {job.id}, Next run: {job.next_run_time}, Args: {job.args}")
            
            # 生成删除报告
            location_desc = f"群聊 {group_id} 中的" if group_id else ""
            
            if len(deleted_reminders) == 1:
                item_type = "任务" if deleted_reminders[0].get("is_task", False) else "提醒"
                return f"已删除{location_desc}{item_type}：{deleted_reminders[0]['text']}"
            else:
                tasks = []
                reminders_list = []
                
                for r in deleted_reminders:
                    if r.get("is_task", False):
                        tasks.append(f"- {r['text']}")
                    else:
                        reminders_list.append(f"- {r['text']}")
                
                result = f"已删除{location_desc} {len(deleted_reminders)} 个项目："
                
                if tasks:
                    result += f"\n\n任务({len(tasks)}):\n" + "\n".join(tasks)
                
                if reminders_list:
                    result += f"\n\n提醒({len(reminders_list)}):\n" + "\n".join(reminders_list)
                
                return result
            
        except Exception as e:
            return f"删除提醒或任务时出错：{str(e)}"

    async def list_all_reminders_and_tasks(self, event: Union[AstrMessageEvent, Context], group_id: str | None = None):
        '''列出当前会话或指定群聊中的所有提醒和任务
        
        Args:
            group_id(string): 可选，指定群聊ID，用于列出特定群聊中的提醒或任务
        '''
        # 权限检查
        if hasattr(event, 'get_sender_id'):
            from .utils import check_permission_and_return_error
            error_msg = check_permission_and_return_error(event, self.star.whitelist)
            if error_msg:
                return error_msg
        
        try:
            if isinstance(event, Context):
                msg_origin = self.context.get_event_queue()._queue[0].session_id
            else:
                creator_id = event.get_sender_id()
                if group_id:
                    # 远程群聊操作
                    from .command_utils import SessionHelper
                    msg_origin = SessionHelper.build_remote_session_id(event, group_id, self.unique_session)
                else:
                    # 本地操作
                    raw_msg_origin = event.unified_msg_origin
                    msg_origin = self.get_session_id(raw_msg_origin, creator_id)
            
            reminders = self.star.compatibility_handler.get_reminders(msg_origin)
            
            from .command_utils import ListGenerator
            return ListGenerator.generate_list_string(reminders)
            
        except Exception as e:
            return f"列出提醒或任务时出错：{str(e)}"