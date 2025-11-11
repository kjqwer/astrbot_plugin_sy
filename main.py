from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api.message_components import *
from astrbot.api.event.filter import command, command_group
from astrbot.api import logger, AstrBotConfig
import os
from pathlib import Path
from .utils import load_reminder_data, CompatibilityHandler
from .scheduler import ReminderScheduler
from .tools import ReminderTools
from .commands import ReminderCommands
from .qq_id_cache import init_qq_id_cache

@register("ai_reminder", "kjqwdw", "智能定时任务，输入/rmd help查看帮助", "1.3.9")
class SmartReminder(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        
        # 保存配置
        self.config = config or {}
        self.unique_session = self.config.get("unique_session", False)
        
        # @功能配置
        self.enable_reminder_at = self.config.get("enable_reminder_at", True)
        self.enable_task_at = self.config.get("enable_task_at", True)
        self.enable_command_at = self.config.get("enable_command_at", False)
        self.hide_command_identifier = self.config.get("hide_command_identifier", False)
        
        # 自定义命令符号配置
        self.custom_command_prefix = self.config.get("custom_command_prefix", "/")
        
        # 用户限制配置
        self.max_reminders_per_user = self.config.get("max_reminders_per_user", 15)
        
        # 指令任务等待时间配置
        self.max_command_wait_time = self.config.get("max_command_wait_time", 20)
        
        # 白名单配置
        self.whitelist = self.config.get("whitelist", "")
        
        # 数据文件路径处理 - 符合框架规范并保持向后兼容
        # 首先检查旧位置是否有数据，如果有则迁移到新位置
        old_data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
        old_data_file = os.path.join(old_data_dir, "reminders", "reminder_data.json")
        
        # 尝试获取新的框架规范路径
        try:
            plugin_data_dir = StarTools.get_data_dir("ai_reminder")
            new_data_file = plugin_data_dir / "reminder_data.json"
            
            # 检查旧位置是否存在数据文件
            if os.path.exists(old_data_file):
                # 旧位置有数据，执行数据迁移
                logger.info(f"检测到旧数据文件，开始数据迁移...")
                logger.info(f"旧位置: {old_data_file}")
                logger.info(f"新位置: {new_data_file}")
                
                # 确保新目录存在
                plugin_data_dir.mkdir(parents=True, exist_ok=True)
                
                # 读取旧数据
                import shutil
                try:
                    # 复制文件到新位置
                    shutil.copy2(old_data_file, new_data_file)
                    logger.info(f"数据迁移成功: {old_data_file} -> {new_data_file}")
                    
                    # 删除旧文件
                    os.remove(old_data_file)
                    logger.info(f"旧数据文件已删除: {old_data_file}")
                    
                    # 使用新位置
                    self.data_file = new_data_file
                    logger.info(f"使用新的框架规范数据目录: {self.data_file}")
                    
                except Exception as e:
                    logger.error(f"数据迁移失败: {e}")
                    # 迁移失败，继续使用旧位置
                    self.data_file = old_data_file
                    logger.info(f"迁移失败，继续使用旧数据目录: {self.data_file}")
            else:
                # 旧位置没有数据，直接使用新位置
                self.data_file = new_data_file
                logger.info(f"使用框架规范数据目录: {self.data_file}")
                
        except Exception as e:
            # 如果框架方法失败，回退到旧的数据目录
            os.makedirs(os.path.join(old_data_dir, "reminders"), exist_ok=True)
            self.data_file = old_data_file
            logger.info(f"回退到兼容数据目录: {self.data_file}")
            logger.warning(f"框架数据目录获取失败: {e}")
        
        # 初始化数据存储
        self.reminder_data = load_reminder_data(str(self.data_file))
        
        # 初始化兼容性处理器（传入context）
        self.compatibility_handler = CompatibilityHandler(self.reminder_data, context)
        
        # 初始化调度器
        self.scheduler_manager = ReminderScheduler(context, self.reminder_data, self.data_file, self.unique_session, self.config)
        
        # 初始化工具
        self.tools = ReminderTools(self)
        
        # 初始化命令
        self.commands = ReminderCommands(self)
        
        # 设置延迟初始化QQ号缓存的定时任务
        self._schedule_qq_id_cache_init()
        
        # 记录配置信息
        logger.info(f"智能提醒插件启动成功，会话隔离：{'启用' if self.unique_session else '禁用'}")
        logger.info(f"上下文功能：{'启用' if self.config.get('enable_context', True) else '禁用'}")
        logger.info(f"最大上下文数量：{self.config.get('max_context_count', 5)}")
        logger.info(f"提醒@功能：{'启用' if self.enable_reminder_at else '禁用'}")
        logger.info(f"任务@功能：{'启用' if self.enable_task_at else '禁用'}")
        logger.info(f"指令任务@功能：{'启用' if self.enable_command_at else '禁用'}")
        logger.info(f"隐藏指令任务标识：{'启用' if self.hide_command_identifier else '禁用'}")
        logger.info(f"自定义命令符号：'{self.custom_command_prefix}' {'(无符号)' if not self.custom_command_prefix else ''}")
        logger.info(f"每用户最大提醒数：{self.max_reminders_per_user if self.max_reminders_per_user > 0 else '不限制'}")
        logger.info(f"指令任务最大等待时间：{self.max_command_wait_time}秒")
        logger.info(f"用户白名单：{'已启用' if self.whitelist.strip() else '未启用'}")

    @filter.llm_tool(name="set_reminder_or_task")
    async def set_reminder_or_task(self, event, text: str, datetime_str: str, is_task: str = "no", user_name: str = "用户", repeat: str | None = None, holiday_type: str | None = None, group_id: str | None = None):
        '''设置一个提醒或任务，到时间后会提醒用户或让AI执行该任务
        
        Args:
            text(string): 提醒内容或任务内容，如果是任务且要调用其他llm函数，请告诉ai（比如，请调用llm函数，内容是...）
            datetime_str(string): 提醒/任务时间，格式为 %Y-%m-%d %H:%M
            is_task(string): 是否为任务，"no"为提醒(到时间提醒用户)，"yes"为任务(到时间让AI执行操作)
            user_name(string): 提醒对象名称，默认为"用户"
            repeat(string): 重复类型，可选值：daily(每天)，weekly(每周)，monthly(每月)，yearly(每年)，none(不重复)。
            holiday_type(string): 可选，节假日类型：workday(仅工作日执行)，holiday(仅法定节假日执行)
            group_id(string): 可选，指定群聊ID，用于在特定群聊中设置提醒或任务
        '''
        is_task_bool = is_task and is_task.lower() == "yes"
        if is_task_bool:
            return await self.tools.set_task(event, text, datetime_str, repeat, holiday_type, group_id)
        else:
            return await self.tools.set_reminder(event, text, datetime_str, user_name, repeat, holiday_type, group_id)

    @filter.llm_tool(name="delete_reminder_or_task")
    async def delete_reminder_or_task(self, event, 
                            content: str | None = None,           # 提醒/任务内容关键词
                            time: str | None = None,              # 具体时间点 HH:MM
                            weekday: str | None = None,           # 星期 mon,tue,wed,thu,fri,sat,sun
                            repeat_type: str | None = None,       # 重复类型 daily,weekly,monthly,yearly,none
                            date: str | None = None,              # 具体日期 YYYY-MM-DD
                            all: str | None = None,               # 是否删除所有 "yes"/"no"
                            task_only: str = "no",         # 是否只删除任务 "yes"/"no"
                            reminder_only: str = "no",     # 是否只删除提醒 "yes"/"no"
                            group_id: str | None = None           # 可选，指定群聊ID
                            ):
        '''删除符合条件的提醒或任务，可组合多个条件进行精确筛选
        
        Args:
            content(string): 可选，提醒或任务内容包含的关键词
            time(string): 可选，具体时间点，格式为 HH:MM，如 "08:00"
            weekday(string): 可选，星期几，可选值：mon,tue,wed,thu,fri,sat,sun
            repeat_type(string): 可选，重复类型，可选值：daily,weekly,monthly,yearly,none
            date(string): 可选，具体日期，格式为 YYYY-MM-DD，如 "2024-02-09"
            all(string): 可选，是否删除所有提醒和任务，可选值：yes/no，默认no
            task_only(string): 可选，是否只删除任务，可选值：yes/no，默认no
            reminder_only(string): 可选，是否只删除提醒，可选值：yes/no，默认no
            group_id(string): 可选，指定群聊ID，用于删除特定群聊中的提醒或任务
        '''
        is_task_only = task_only and task_only.lower() == "yes"
        is_reminder_only = reminder_only and reminder_only.lower() == "yes"
        return await self.tools.delete_reminder(event, content, time, weekday, repeat_type, date, all, 
                                               "yes" if is_task_only else "no", 
                                               "yes" if is_reminder_only else "no", 
                                               group_id)

    @filter.llm_tool(name="list_reminders_and_tasks")
    async def list_all_reminders_and_tasks(self, event, group_id: str | None = None):
        '''列出当前会话或指定群聊中的所有提醒和任务
        
        Args:
            group_id(string): 可选，指定群聊ID，用于列出特定群聊中的提醒或任务
        '''
        return await self.tools.list_all_reminders_and_tasks(event, group_id)
        
    # 命令组必须定义在主类中
    @command_group("rmd")
    def rmd(self):
        '''提醒相关命令'''
        pass

    @rmd.command("ls")
    async def list_reminders(self, event: AstrMessageEvent):
        '''列出所有提醒和任务'''
        async for result in self.commands.list_reminders(event):
            yield result

    @rmd.command("rm")
    async def remove_reminder(self, event: AstrMessageEvent, index: int):
        '''删除提醒或任务
        
        Args:
            index(int): 提醒或任务的序号
        '''
        async for result in self.commands.remove_reminder(event, index):
            yield result

    @rmd.command("add")
    async def add_reminder(self, event: AstrMessageEvent, text: str, time_str: str, week: str | None = None, repeat: str | None = None, holiday_type: str | None = None):
        '''手动添加提醒
        
        Args:
            text(string): 提醒内容
            time_str(string): 时间，格式为 HH:MM 或 HHMM
            week(string): 可选，开始星期：mon,tue,wed,thu,fri,sat,sun
            repeat(string): 可选，重复类型：daily,weekly,monthly,yearly,none或带节假日类型的组合（如daily workday）
            holiday_type(string): 可选，节假日类型：workday(仅工作日执行)，holiday(仅法定节假日执行)
        '''
        async for result in self.commands.add_reminder(event, text, time_str, week, repeat, holiday_type):
            yield result

    @rmd.command("task")
    async def add_task(self, event: AstrMessageEvent, text: str, time_str: str, week: str | None = None, repeat: str | None = None, holiday_type: str | None = None):
        '''手动添加任务
        
        Args:
            text(string): 任务内容
            time_str(string): 时间，格式为 HH:MM 或 HHMM
            week(string): 可选，开始星期：mon,tue,wed,thu,fri,sat,sun
            repeat(string): 可选，重复类型：daily,weekly,monthly,yearly,none或带节假日类型的组合（如daily workday）
            holiday_type(string): 可选，节假日类型：workday(仅工作日执行)，holiday(仅法定节假日执行)
        '''
        async for result in self.commands.add_task(event, text, time_str, week, repeat, holiday_type):
            yield result

    @rmd.command("help")
    async def show_help(self, event: AstrMessageEvent):
        '''显示帮助信息'''
        async for result in self.commands.show_help(event):
            yield result

    @rmd.command("command")
    async def add_command_task(self, event: AstrMessageEvent, command: str, time_str: str, week: str | None = None, repeat: str | None = None, holiday_type: str | None = None):
        '''设置指令任务
        
        Args:
            command(string): 要执行的指令，如"/memory_config"或"/rmd--ls----before--要说的话"或"/rmd--ls----after--要说的话"
            time_str(string): 时间，格式为 HH:MM 或 HHMM
            week(string): 可选，开始星期：mon,tue,wed,thu,fri,sat,sun
            repeat(string): 可选，重复类型：daily,weekly,monthly,yearly
            holiday_type(string): 可选，节假日类型：workday(仅工作日执行)，holiday(仅法定节假日执行)
        '''
        async for result in self.commands.add_command_task(event, command, time_str, week, repeat, holiday_type):
            yield result

    # 远程群聊指令组
    @command_group("rmdg")
    def rmdg(self):
        '''远程群聊提醒相关命令'''
        pass

    @rmdg.command("add")
    async def add_remote_reminder(self, event: AstrMessageEvent, group_id: str, text: str, time_str: str, week: str | None = None, repeat: str | None = None, holiday_type: str | None = None):
        '''在指定群聊中手动添加提醒
        
        Args:
            group_id(string): 群聊ID
            text(string): 提醒内容
            time_str(string): 时间，格式为 HH:MM 或 HHMM
            week(string): 可选，开始星期：mon,tue,wed,thu,fri,sat,sun
            repeat(string): 可选，重复类型：daily,weekly,monthly,yearly或带节假日类型的组合（如daily workday）
            holiday_type(string): 可选，节假日类型：workday(仅工作日执行)，holiday(仅法定节假日执行)
        '''
        async for result in self.commands.add_remote_reminder(event, group_id, text, time_str, week, repeat, holiday_type):
            yield result

    @rmdg.command("task")
    async def add_remote_task(self, event: AstrMessageEvent, group_id: str, text: str, time_str: str, week: str | None = None, repeat: str | None = None, holiday_type: str | None = None):
        '''在指定群聊中手动添加任务
        
        Args:
            group_id(string): 群聊ID
            text(string): 任务内容
            time_str(string): 时间，格式为 HH:MM 或 HHMM
            week(string): 可选，开始星期：mon,tue,wed,thu,fri,sat,sun
            repeat(string): 可选，重复类型：daily,weekly,monthly,yearly或带节假日类型的组合（如daily workday）
            holiday_type(string): 可选，节假日类型：workday(仅工作日执行)，holiday(仅法定节假日执行)
        '''
        async for result in self.commands.add_remote_task(event, group_id, text, time_str, week, repeat, holiday_type):
            yield result

    @rmdg.command("command")
    async def add_remote_command_task(self, event: AstrMessageEvent, group_id: str, command: str, time_str: str, week: str | None = None, repeat: str | None = None, holiday_type: str | None = None):
        '''在指定群聊中设置指令任务
        
        Args:
            group_id(string): 群聊ID
            command(string): 要执行的指令，如"/memory_config"或"/rmd--ls----before--要说的话"或"/rmd--ls----after--要说的话"
            time_str(string): 时间，格式为 HH:MM 或 HHMM
            week(string): 可选，开始星期：mon,tue,wed,thu,fri,sat,sun
            repeat(string): 可选，重复类型：daily,weekly,monthly,yearly
            holiday_type(string): 可选，节假日类型：workday(仅工作日执行)，holiday(仅法定节假日执行)
        '''
        async for result in self.commands.add_remote_command_task(event, group_id, command, time_str, week, repeat, holiday_type):
            yield result

    @rmdg.command("help")
    async def show_remote_help(self, event: AstrMessageEvent):
        '''显示远程群聊帮助信息'''
        async for result in self.commands.show_remote_help(event):
            yield result

    @rmdg.command("ls")
    async def list_remote_reminders(self, event: AstrMessageEvent, group_id: str):
        '''列出指定群聊中的所有提醒和任务
        
        Args:
            group_id(string): 群聊ID
        '''
        async for result in self.commands.list_remote_reminders(event, group_id):
            yield result

    @rmdg.command("rm")
    async def remove_remote_reminder(self, event: AstrMessageEvent, group_id: str, index: int):
        '''删除指定群聊中的提醒或任务
        
        Args:
            group_id(string): 群聊ID
            index(int): 提醒或任务的序号
        '''
        async for result in self.commands.remove_remote_reminder(event, group_id, index):
            yield result


    def _schedule_qq_id_cache_init(self):
        """设置延迟初始化QQ号缓存的定时任务"""
        import asyncio
        
        async def delayed_init():
            # 等待8秒确保平台完全加载
            await asyncio.sleep(8)
            try:
                logger.info("开始延迟初始化QQ号缓存")
                init_qq_id_cache(self.context)
                logger.info("QQ号缓存初始化完成")
            except Exception as e:
                logger.warning(f"QQ号缓存初始化失败: {e}")
        
        # 创建异步任务
        asyncio.create_task(delayed_init())

