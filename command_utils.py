import re
import datetime
from typing import List, Tuple, Optional, Dict, Any
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent


class CommandUtils:
    """命令工具类，用于处理多命令指令"""
    
    @staticmethod
    def parse_multi_command(command: str) -> Tuple[str, List[str], Optional[dict]]:
        """
        解析命令字符串，处理包含 "--" 的完整指令和 "----" 的自定义标识
        
        Args:
            command: 原始命令字符串，如 "/rmd--ls" 或 "/rmd--ls----决定是放在开头还是末尾的指令--要说的话"
            
        Returns:
            Tuple[str, List[str], Optional[dict]]: (显示命令, 执行命令列表, 自定义标识信息)
            - 显示命令: 用于显示的命令字符串，保持原始格式
            - 执行命令列表: 处理后的命令列表，用于实际执行
            - 自定义标识信息: 包含自定义文字和位置的字典，如果没有则为None
        """
        # 首先检查是否包含 "----" 分隔符（自定义标识）
        custom_identifier = None
        if "----" in command:
            parts = command.split("----")
            if len(parts) >= 2:
                # 提取自定义标识信息
                command_part = parts[0].strip()
                custom_part = parts[1].strip()
                
                # 解析自定义标识
                custom_identifier = CommandUtils._parse_custom_identifier(custom_part)
                
                # 使用处理后的命令部分继续解析
                command = command_part
        
        # 检查是否包含 "--" 分隔符
        if "--" in command:
            # 使用 "--" 分割命令
            parts = command.split("--")
            # 过滤空字符串并去除首尾空格
            parts = [part.strip() for part in parts if part.strip()]
            
            if len(parts) == 0:
                return command, [], custom_identifier
            elif len(parts) == 1:
                # 只有一个部分，直接返回
                return command, [parts[0]], custom_identifier
            else:
                # 多个部分，需要组合成完整指令
                # 第一个部分应该是主命令（如 /rmd），其余部分是子命令
                main_cmd = parts[0]
                sub_cmds = parts[1:]
                
                # 组合成完整的指令
                full_command = main_cmd + " " + " ".join(sub_cmds)
                
                # 显示命令保持原始格式（如 /rmd--ls），执行命令是组合后的完整指令（如 /rmd ls）
                return command, [full_command], custom_identifier
        else:
            # 没有 "--" 分隔符，这是单个命令
            return command, [command], custom_identifier
    
    @staticmethod
    def _parse_custom_identifier(custom_part: str) -> Optional[dict]:
        """
        解析自定义标识部分
        
        Args:
            custom_part: 自定义标识字符串，如 "决定是放在开头还是末尾的指令--要说的话"
            
        Returns:
            Optional[dict]: 包含自定义文字和位置的字典，格式为：
            {
                "text": "要说的话",
                "position": "start" 或 "end"
            }
        """
        if not custom_part:
            return None
            
        # 检查是否包含 "--" 分隔符来分割位置和文字
        if "--" in custom_part:
            parts = custom_part.split("--")
            if len(parts) >= 2:
                position_part = parts[0].strip()
                text_part = parts[1].strip()
                
                # 判断位置
                position = "start"  # 默认放在开头
                if "末尾" in position_part or "后面" in position_part or "end" in position_part.lower() or "after" in position_part.lower():
                    position = "end"
                elif "开头" in position_part or "前面" in position_part or "start" in position_part.lower() or "before" in position_part.lower():
                    position = "start"
                
                return {
                    "text": text_part,
                    "position": position
                }
        
        # 如果没有 "--" 分隔符，整个字符串作为文字，默认放在开头
        return {
            "text": custom_part,
            "position": "start"
        }
    
    @staticmethod
    def validate_commands(commands: List[str], custom_prefix: str = "/") -> Tuple[bool, str]:
        """
        验证命令列表的有效性
        
        Args:
            commands: 命令列表
            custom_prefix: 自定义命令符号，默认为"/"，可以为空字符串表示无需符号
            
        Returns:
            Tuple[bool, str]: (是否有效, 错误信息)
        """
        if not commands:
            return False, "没有有效的命令"
        
        for i, cmd in enumerate(commands):
            # 如果自定义前缀为空，则不检查前缀
            if custom_prefix and not cmd.startswith(custom_prefix):
                return False, f"命令 {i+1} 格式错误，必须以 {custom_prefix} 开头：{cmd}"
            
            # 检查命令长度
            if len(cmd) < 1:
                return False, f"命令 {i+1} 太短：{cmd}"
            
            # 如果有前缀，检查去掉前缀后的长度
            if custom_prefix and len(cmd) <= len(custom_prefix):
                return False, f"命令 {i+1} 太短：{cmd}"
        
        return True, ""
    
    @staticmethod
    def format_command_display(display_command: str, commands: List[str]) -> str:
        """
        格式化命令显示信息
        
        Args:
            display_command: 原始显示命令
            commands: 执行命令列表
            
        Returns:
            str: 格式化后的显示信息
        """
        # 直接返回原始显示命令，保持用户输入的格式
        return display_command
    
    @staticmethod
    def get_command_description(commands: List[str]) -> str:
        """
        获取命令描述信息
        
        Args:
            commands: 命令列表
            
        Returns:
            str: 命令描述
        """
        # 现在只处理单个指令，commands列表应该只有一个元素
        if len(commands) == 1:
            return f"执行指令：{commands[0]}"
        else:
            # 这种情况理论上不应该发生，但为了安全起见
            return f"执行指令：{' '.join(commands)}"


class ParameterValidator:
    """参数验证工具类，用于统一处理重复的参数验证逻辑"""
    
    # 常量定义
    WEEK_MAP = {
        'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 
        'fri': 4, 'sat': 5, 'sun': 6
    }
    
    REPEAT_TYPES = ["daily", "weekly", "monthly", "yearly", "none"]
    HOLIDAY_TYPES = ["workday", "holiday"]
    
    @staticmethod
    def validate_and_adjust_parameters(week: Optional[str] = None, repeat: Optional[str] = None, holiday_type: Optional[str] = None) -> Tuple[bool, str, Optional[str], Optional[str], Optional[str]]:
        """
        验证并调整参数，处理参数错位的情况
        
        Args:
            week: 星期参数
            repeat: 重复类型参数
            holiday_type: 节假日类型参数
            
        Returns:
            Tuple[bool, str, Optional[str], Optional[str], Optional[str]]: 
            (是否成功, 错误信息, 调整后的week, 调整后的repeat, 调整后的holiday_type)
        """
        # 改进的参数处理逻辑：尝试调整星期和重复类型参数
        if week and week.lower() not in ParameterValidator.WEEK_MAP:
            # 星期格式错误，尝试将其作为repeat处理
            if week.lower() in ParameterValidator.REPEAT_TYPES or week.lower() in ParameterValidator.HOLIDAY_TYPES:
                # week参数实际上可能是repeat参数
                if repeat:
                    # 如果repeat也存在，则将week和repeat作为组合
                    holiday_type = repeat  # 将原来的repeat视为holiday_type
                    repeat = week  # 将原来的week视为repeat
                else:
                    repeat = week  # 将原来的week视为repeat
                week = None  # 清空week，使用默认值（今天）
                logger.info(f"已将'{week}'识别为重复类型，默认使用今天作为开始日期")
            else:
                return False, "星期格式错误，可选值：mon,tue,wed,thu,fri,sat,sun", None, None, None

        # 特殊处理: 检查repeat是否包含节假日类型信息
        if repeat:
            parts = repeat.split()
            if len(parts) == 2 and parts[1] in ParameterValidator.HOLIDAY_TYPES:
                # 如果repeat参数包含两部分，且第二部分是workday或holiday
                repeat = parts[0]  # 提取重复类型
                holiday_type = parts[1]  # 提取节假日类型

        # 验证重复类型
        if repeat and repeat.lower() not in ParameterValidator.REPEAT_TYPES:
            return False, "重复类型错误，可选值：daily,weekly,monthly,yearly,none", None, None, None
            
        # 验证节假日类型
        if holiday_type and holiday_type.lower() not in ParameterValidator.HOLIDAY_TYPES:
            return False, "节假日类型错误，可选值：workday(仅工作日执行)，holiday(仅法定节假日执行)", None, None, None

        return True, "", week, repeat, holiday_type


class DateTimeProcessor:
    """日期时间处理工具类"""
    
    @staticmethod
    def adjust_datetime_for_week(dt: datetime.datetime, week: Optional[str] = None) -> datetime.datetime:
        """
        根据指定星期调整日期时间
        
        Args:
            dt: 原始日期时间
            week: 星期参数
            
        Returns:
            datetime.datetime: 调整后的日期时间
        """
        if week:
            target_weekday = ParameterValidator.WEEK_MAP[week.lower()]
            current_weekday = dt.weekday()
            days_ahead = target_weekday - current_weekday
            if days_ahead <= 0:  # 如果目标星期已过，调整到下周
                days_ahead += 7
            dt += datetime.timedelta(days=days_ahead)
        return dt
    
    @staticmethod
    def build_final_repeat(repeat: Optional[str] = None, holiday_type: Optional[str] = None) -> str:
        """
        构建最终的重复类型字符串
        
        Args:
            repeat: 重复类型
            holiday_type: 节假日类型
            
        Returns:
            str: 最终的重复类型字符串
        """
        final_repeat = repeat.lower() if repeat else "none"
        if repeat and holiday_type:
            final_repeat = f"{repeat.lower()}_{holiday_type.lower()}"
        return final_repeat


class RepeatDescriptionGenerator:
    """重复类型描述生成器"""
    
    @staticmethod
    def generate_repeat_description(repeat: Optional[str] = None, holiday_type: Optional[str] = None) -> str:
        """
        根据重复类型和节假日类型生成文本说明
        
        Args:
            repeat: 重复类型
            holiday_type: 节假日类型
            
        Returns:
            str: 重复类型描述
        """
        if repeat == "daily" and not holiday_type:
            return "每天重复"
        elif repeat == "daily" and holiday_type == "workday":
            return "每个工作日重复（法定节假日不触发）"
        elif repeat == "daily" and holiday_type == "holiday":
            return "每个法定节假日重复"
        elif repeat == "weekly" and not holiday_type:
            return "每周重复"
        elif repeat == "weekly" and holiday_type == "workday":
            return "每周的这一天重复，但仅工作日触发"
        elif repeat == "weekly" and holiday_type == "holiday":
            return "每周的这一天重复，但仅法定节假日触发"
        elif repeat == "monthly" and not holiday_type:
            return "每月重复"
        elif repeat == "monthly" and holiday_type == "workday":
            return "每月的这一天重复，但仅工作日触发"
        elif repeat == "monthly" and holiday_type == "holiday":
            return "每月的这一天重复，但仅法定节假日触发"
        elif repeat == "yearly" and not holiday_type:
            return "每年重复"
        elif repeat == "yearly" and holiday_type == "workday":
            return "每年的这一天重复，但仅工作日触发"
        elif repeat == "yearly" and holiday_type == "holiday":
            return "每年的这一天重复，但仅法定节假日触发"
        else:
            return "一次性"


class ItemBuilder:
    """数据项构建器"""
    
    @staticmethod
    def build_reminder_item(text: str, dt: datetime.datetime, creator_id: str, creator_name: Optional[str],
                          final_repeat: str, target_user_id: Optional[str] = None) -> Dict[str, Any]:
        """构建提醒数据项"""
        # 如果指定了目标用户ID，则使用目标用户ID，否则使用创建者ID
        actual_creator_id = target_user_id if target_user_id else creator_id
        return {
            "text": text,
            "datetime": dt.strftime("%Y-%m-%d %H:%M"),
            "user_name": creator_name or creator_id,  # 优先使用昵称，回退到ID
            "repeat": final_repeat,
            "creator_id": actual_creator_id,  # 使用实际的目标用户ID
            "creator_name": creator_name,
            "is_task": False
        }
    
    @staticmethod
    def build_task_item(text: str, dt: datetime.datetime, creator_id: str, creator_name: Optional[str],
                       final_repeat: str, target_user_id: Optional[str] = None) -> Dict[str, Any]:
        """构建任务数据项"""
        # 如果指定了目标用户ID，则使用目标用户ID，否则使用创建者ID
        actual_creator_id = target_user_id if target_user_id else creator_id
        return {
            "text": text,
            "datetime": dt.strftime("%Y-%m-%d %H:%M"),
            "user_name": creator_name or creator_id,  # 优先使用昵称，回退到ID
            "repeat": final_repeat,
            "creator_id": actual_creator_id,  # 使用实际的目标用户ID
            "creator_name": creator_name,
            "is_task": True
        }
    
    @staticmethod
    def build_command_task_item(clean_display_command: str, commands: List[str], dt: datetime.datetime, 
                               creator_id: str, creator_name: Optional[str], final_repeat: str,
                               custom_identifier: Optional[dict] = None) -> Dict[str, Any]:
        """构建指令任务数据项"""
        return {
            "text": clean_display_command,
            "commands": commands,
            "datetime": dt.strftime("%Y-%m-%d %H:%M"),
            "user_name": creator_name or creator_id, 
            "repeat": final_repeat,
            "creator_id": creator_id,
            "creator_name": creator_name,
            "is_task": True,
            "is_command_task": True,
            "custom_identifier": custom_identifier
        }


class SessionHelper:
    """会话辅助工具类"""
    
    @staticmethod
    def get_session_info(event: AstrMessageEvent, unique_session: bool) -> Tuple[str, str, str]:
        """
        获取会话相关信息
        
        Args:
            event: 消息事件
            unique_session: 是否启用会话隔离
            
        Returns:
            Tuple[str, str, str]: (creator_id, raw_msg_origin, msg_origin)
        """
        creator_id = event.get_sender_id()
        raw_msg_origin = event.unified_msg_origin
        
        if unique_session:
            # 使用会话隔离 - 直接实现逻辑，避免依赖tools
            msg_origin = SessionHelper._get_session_id_with_isolation(raw_msg_origin, creator_id)
        else:
            msg_origin = raw_msg_origin
            
        return creator_id, raw_msg_origin, msg_origin
    
    @staticmethod
    def _get_session_id_with_isolation(msg_origin: str, creator_id: Optional[str] = None) -> str:
        """
        根据会话隔离设置，获取正确的会话ID
        
        Args:
            msg_origin: 原始会话ID
            creator_id: 创建者ID
            
        Returns:
            str: 处理后的会话ID
        """
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
    
    @staticmethod
    def get_creator_info(event: AstrMessageEvent) -> Tuple[str, Optional[str]]:
        """
        获取创建者信息
        
        Args:
            event: 消息事件
            
        Returns:
            Tuple[str, Optional[str]]: (creator_id, creator_name)
        """
        creator_id = event.get_sender_id()
        creator_name = None
        
        # 尝试多种方式获取用户昵称
        try:
            # 首先尝试使用 get_sender_name() 方法
            creator_name = event.get_sender_name()
            if not creator_name:
                # 如果为空，再尝试直接访问属性
                if hasattr(event.message_obj, 'sender') and hasattr(event.message_obj.sender, 'nickname'):
                    creator_name = event.message_obj.sender.nickname
        except Exception as e:
            logger.warning(f"获取用户昵称失败: {e}")
            
        return creator_id, creator_name
    
    @staticmethod
    async def find_user_id_by_name(event: AstrMessageEvent, user_name: str) -> Optional[str]:
        """
        根据用户名查找用户ID（仅在群聊中有效）
        
        Args:
            event: 消息事件
            user_name: 要查找的用户名
            
        Returns:
            Optional[str]: 找到的用户ID，如果未找到则返回None
        """
        # 只在群聊中进行查找
        if event.is_private_chat():
            return None
            
        try:
            group_id = int(event.get_group_id())
            # 获取群成员列表
            members = await event.bot.get_group_member_list(group_id=group_id)
            
            # 遍历成员列表，查找匹配的用户名
            for member in members:
                if member.get("user_id"):
                    # 检查昵称或群名片是否匹配
                    nickname = member.get("nickname", "")
                    card = member.get("card", "")
                    
                    # 优先匹配群名片，其次匹配昵称
                    if (card and card == user_name) or (nickname and nickname == user_name):
                        return str(member["user_id"])
                        
        except Exception as e:
            logger.warning(f"查找用户ID失败: {e}")
            
        return None
    
    @staticmethod
    def build_remote_session_id(event: AstrMessageEvent, group_id: str, unique_session: bool) -> str:
        """
        构建远程群聊的会话ID
        
        Args:
            event: 消息事件
            group_id: 群聊ID
            unique_session: 是否启用会话隔离
            
        Returns:
            str: 会话ID
        """
        creator_id = event.get_sender_id()
        
        # 获取平台ID（兼容v3/v4）
        try:
            # 优先使用事件对象的方法获取平台ID
            platform_id = event.get_platform_id() if hasattr(event, 'get_platform_id') else 'unknown'
            if platform_id == 'unknown':
                # 如果失败，尝试从origin解析
                from .utils import get_platform_id_from_origin
                platform_id = get_platform_id_from_origin(event.unified_msg_origin)
        except:
            platform_id = 'unknown'
        
        if unique_session:
            # 使用会话隔离
            return f"{platform_id}:GroupMessage:{group_id}_{creator_id}"
        else:
            return f"{platform_id}:GroupMessage:{group_id}"


class ResultFormatter:
    """结果格式化工具类"""
    
    @staticmethod
    def format_success_message(item_type: str, text: str, dt: datetime.datetime,
                             start_str: str, repeat_str: str, group_id: Optional[str] = None) -> str:
        """
        格式化成功消息
        
        Args:
            item_type: 项目类型（提醒/任务/指令任务）
            text: 内容
            dt: 日期时间
            start_str: 开始时间描述
            repeat_str: 重复类型描述
            group_id: 群聊ID（可选）
            
        Returns:
            str: 格式化后的消息
        """
        location_str = f"在群聊 {group_id} " if group_id else ""
        
        if item_type == "指令任务":
            command_desc = CommandUtils.get_command_description([text]) if isinstance(text, str) else text
            return f"已{location_str}设置指令任务:\n{command_desc}\n时间: {dt.strftime('%Y-%m-%d %H:%M')}\n{start_str}{repeat_str}\n\n使用 /rmd ls 查看所有提醒和任务"
        else:
            return f"已{location_str}设置{item_type}:\n内容: {text}\n时间: {dt.strftime('%Y-%m-%d %H:%M')}\n{start_str}{repeat_str}\n\n使用 /rmd ls 查看所有提醒和任务"
    
    @staticmethod
    def get_week_start_description(dt: datetime.datetime, week: Optional[str] = None) -> str:
        """
        获取星期开始描述
        
        Args:
            dt: 日期时间
            week: 星期参数
            
        Returns:
            str: 星期开始描述
        """
        if not week:
            return ""
        
        week_names = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
        return f"从{week_names[dt.weekday()]}开始，"


class UnifiedCommandProcessor:
    """统一命令处理器，整合所有添加操作的通用逻辑"""
    
    def __init__(self, star_instance):
        """
        初始化处理器
        
        Args:
            star_instance: 主插件实例
        """
        self.star = star_instance
        self.context = star_instance.context
        self.reminder_data = star_instance.reminder_data
        self.data_file = star_instance.data_file
        self.scheduler_manager = star_instance.scheduler_manager
        self.unique_session = star_instance.unique_session
        # 移除对tools的直接引用，避免循环依赖
        self.custom_command_prefix = star_instance.custom_command_prefix
    
    async def process_add_item(self, event: AstrMessageEvent, item_type: str, content: str,
                              time_str: str, week: Optional[str] = None, repeat: Optional[str] = None,
                              holiday_type: Optional[str] = None, group_id: Optional[str] = None,
                              time_already_parsed: bool = False, user_name: Optional[str] = None):
        """
        统一处理添加项目的逻辑
        
        Args:
            event: 消息事件
            item_type: 项目类型 ('reminder', 'task', 'command_task')
            content: 内容（提醒文本、任务文本或命令）
            time_str: 时间字符串
            week: 星期参数
            repeat: 重复类型
            holiday_type: 节假日类型
            group_id: 群聊ID（远程操作时使用）
            time_already_parsed: 时间是否已经解析过（LLM工具使用）
            
        Yields:
            消息结果
        """
        try:
            # 1. 解析时间
            if time_already_parsed:
                # 时间已经解析过，直接使用
                datetime_str = time_str
            else:
                # 需要解析时间（手动命令使用）
                from .utils import parse_datetime
                try:
                    datetime_str = parse_datetime(time_str)
                except ValueError as e:
                    yield event.plain_result(str(e))
                    return

            # 2. 验证并调整参数
            success, error_msg, week, repeat, holiday_type = ParameterValidator.validate_and_adjust_parameters(
                week, repeat, holiday_type
            )
            if not success:
                yield event.plain_result(error_msg)
                return

            # 3. 处理特殊的指令任务逻辑
            commands: Optional[List[str]] = None
            custom_identifier = None
            clean_display_command = content
            
            if item_type == 'command_task':
                # 解析多命令指令
                display_command, commands, custom_identifier = CommandUtils.parse_multi_command(content)
                
                # 验证命令列表
                if commands:
                    is_valid, error_msg = CommandUtils.validate_commands(commands, self.custom_command_prefix)
                    if not is_valid:
                        yield event.plain_result(f"指令格式错误：{error_msg}")
                        return
                else:
                    yield event.plain_result("指令格式错误：未能解析出有效指令。")
                    return

                # 格式化显示命令
                clean_display_command = CommandUtils.format_command_display(display_command, commands)

            # 4. 获取会话信息
            creator_id, creator_name = SessionHelper.get_creator_info(event)
            
            if group_id:
                # 远程群聊操作
                msg_origin = SessionHelper.build_remote_session_id(event, group_id, self.unique_session)
            else:
                # 本地操作
                _creator_id, raw_msg_origin, msg_origin = SessionHelper.get_session_info(
                    event, self.unique_session
                )
                # 确保 creator_id 和 creator_name 是从 get_creator_info 获取的
                creator_id = _creator_id

            # 4.1. 在群聊中根据user_name查找目标用户ID（仅对提醒和任务生效）
            target_user_id = None
            if item_type in ['reminder', 'task'] and user_name and event.get_group_id():
                try:
                    target_user_id = await SessionHelper.find_user_id_by_name(event, user_name)
                except Exception as e:
                    # 查找失败时保持原有逻辑，使用设置者的ID
                    pass

            # 5. 确保key存在
            actual_key = self.star.compatibility_handler.ensure_key_exists(msg_origin)

            # 5.1. 检查提醒数量限制
            from .utils import check_reminder_limit
            can_create, error_msg = check_reminder_limit(
                self.reminder_data, 
                actual_key, 
                self.star.max_reminders_per_user, 
                self.unique_session, 
                creator_id
            )
            if not can_create:
                yield event.plain_result(error_msg)
                return

            # 6. 处理日期时间
            dt = datetime.datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
            dt = DateTimeProcessor.adjust_datetime_for_week(dt, week)

            # 7. 构建最终重复类型
            final_repeat = DateTimeProcessor.build_final_repeat(repeat, holiday_type)

            # 8. 构建数据项
            if item_type == 'command_task':
                if commands:
                    item = ItemBuilder.build_command_task_item(
                        clean_display_command, commands, dt, creator_id, creator_name,
                        final_repeat, custom_identifier
                    )
                else:
                    # This case should ideally not be reached if validation is correct
                    yield event.plain_result("创建指令任务失败：无效的指令。")
                    return
            elif item_type == 'task':
                item = ItemBuilder.build_task_item(
                    content, dt, creator_id, creator_name, final_repeat, target_user_id
                )
            else:  # reminder
                item = ItemBuilder.build_reminder_item(
                    content, dt, creator_id, creator_name, final_repeat, target_user_id
                )

            # 9. 保存数据
            self.reminder_data[actual_key].append(item)

            # 10. 设置定时任务并保存任务ID
            job_id = self.scheduler_manager.add_job(actual_key, item, dt)
            item["job_id"] = job_id  # 保存任务ID到数据中

            # 11. 保存数据文件
            from .utils import save_reminder_data
            await save_reminder_data(self.data_file, self.reminder_data)

            # 12. 生成并返回成功消息
            start_str = ResultFormatter.get_week_start_description(dt, week)
            repeat_str = RepeatDescriptionGenerator.generate_repeat_description(repeat, holiday_type)
            
            # 确定项目类型名称
            type_names = {
                'reminder': '提醒',
                'task': '任务',
                'command_task': '指令任务'
            }
            type_name = type_names.get(item_type, '项目')
            
            # 格式化成功消息
            if item_type == 'command_task':
                if commands:
                    command_desc = CommandUtils.get_command_description(commands)
                else:
                    command_desc = ""
                success_msg = ResultFormatter.format_success_message(
                    type_name, command_desc, dt, start_str, repeat_str, group_id
                )
            else:
                success_msg = ResultFormatter.format_success_message(
                    type_name, content, dt, start_str, repeat_str, group_id
                )
            
            yield event.plain_result(success_msg)

        except Exception as e:
            item_type_name = {'reminder': '提醒', 'task': '任务', 'command_task': '指令任务'}.get(item_type, '项目')
            yield event.plain_result(f"设置{item_type_name}时出错：{str(e)}")