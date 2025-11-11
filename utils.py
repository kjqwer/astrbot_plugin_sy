import datetime
import json
import os
import aiohttp
from astrbot.api import logger

def parse_datetime_for_llm(datetime_str: str) -> str:
    '''专门为LLM工具解析时间字符串，只处理标准格式 %Y-%m-%d %H:%M'''
    try:
        datetime_str = datetime_str.strip()
        
        # 支持中文冒号和英文冒号
        datetime_str = datetime_str.replace('：', ':')
        
        # 尝试直接解析标准格式：YYYY-MM-DD HH:MM
        try:
            dt = datetime.datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
            
            # 检查时间是否在过去（如果是过去时间，AI可能设置错了时间）
            now = datetime.datetime.now()
            if dt < now:
                # 如果是过去的时间，我们假设AI想要设置明天的同一时间
                # 或者如果是当年但过去的日期，调整为明年
                if dt.date() < now.date():
                    if dt.year == now.year:
                        # 同年但过去的日期，调整为明年
                        dt = dt.replace(year=now.year + 1)
                    # 如果年份本身就是过去的，保持不变，可能AI故意设置历史时间
                logger.info(f"时间调整: 原时间 '{datetime_str}' 在过去，调整为 '{dt.strftime('%Y-%m-%d %H:%M')}'")
            
            logger.info(f"LLM时间解析成功: '{datetime_str}' -> {dt.strftime('%Y-%m-%d %H:%M')}")
            return dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            # 如果标准格式失败，尝试其他常见格式
            formats = [
                "%Y-%m-%d %H:%M:%S",  # 带秒数
                "%Y/%m/%d %H:%M",     # 斜杠分隔
                "%Y/%m/%d %H:%M:%S",  # 斜杠分隔带秒数
            ]
            
            for fmt in formats:
                try:
                    dt = datetime.datetime.strptime(datetime_str, fmt)
                    logger.info(f"LLM时间解析成功 (格式 {fmt}): '{datetime_str}' -> {dt.strftime('%Y-%m-%d %H:%M')}")
                    return dt.strftime("%Y-%m-%d %H:%M")
                except ValueError:
                    continue
            
            # 所有格式都失败
            raise ValueError(f"无法解析时间格式: {datetime_str}，请使用 YYYY-MM-DD HH:MM 格式")
            
    except Exception as e:
        logger.error(f"LLM时间解析失败: '{datetime_str}', 错误: {str(e)}")
        raise ValueError(f"时间格式错误: {str(e)}")

def parse_datetime(datetime_str: str) -> str:
    '''解析时间字符串，支持多种时间格式'''
    original_input = datetime_str
    try:
        today = datetime.datetime.now()
        
        # 记录原始输入
        logger.info(f"parse_datetime 收到输入: '{original_input}'")
        
        # 处理输入字符串，去除多余空格
        datetime_str = datetime_str.strip()
        
        # 支持中文冒号和英文冒号
        datetime_str = datetime_str.replace('：', ':')
        
        # 尝试解析全连字符格式（如：2025-09-17-06:00 或 09-17-06:00）
        if '-' in datetime_str and ':' in datetime_str:
            # logger.info(f"尝试解析全连字符格式: '{datetime_str}'")
            try:
                parts = datetime_str.split('-')
                logger.info(f"分割结果: {parts}, 长度: {len(parts)}")
                if len(parts) == 4:  # 格式：YYYY-MM-DD-HH:MM
                    year = int(parts[0])
                    month = int(parts[1])
                    day = int(parts[2])
                    time_part = parts[3]
                    if ':' in time_part:
                        hour, minute = map(int, time_part.split(':'))
                    else:
                        raise ValueError("时间部分格式错误")
                    
                    # 验证日期时间有效性
                    dt = datetime.datetime(year, month, day, hour, minute)
                    
                    # 检查时间是否在过去，如果是过去的年份则调整
                    if dt.year < today.year:
                        dt = dt.replace(year=today.year)
                    # 如果时间已过且不是当前时间（精确到分钟），调整为明年
                    current_time_min = today.replace(second=0, microsecond=0)
                    if dt < today and dt != current_time_min:
                        dt = dt.replace(year=today.year + 1)
                    
                    return dt.strftime("%Y-%m-%d %H:%M")
                    
                elif len(parts) == 3:  # 格式：MM-DD-HH:MM（只有月份）
                    month = int(parts[0])
                    day = int(parts[1])
                    time_part = parts[2]
                    if ':' in time_part:
                        hour, minute = map(int, time_part.split(':'))
                    else:
                        raise ValueError("时间部分格式错误")
                    
                    # 使用今年作为默认年份
                    year = today.year
                    dt = datetime.datetime(year, month, day, hour, minute)
                    
                    # 如果时间已过且不是当前时间（精确到分钟），使用明年
                    current_time_min = today.replace(second=0, microsecond=0)
                    if dt < today and dt != current_time_min:
                        dt = dt.replace(year=year + 1)
                    
                    return dt.strftime("%Y-%m-%d %H:%M")
                else:
                    # 如果分割结果不是3或4个部分，格式不正确
                    raise ValueError(f"分割结果长度错误: {len(parts)}")
            except ValueError as e:
                logger.error(f"全连字符格式解析失败: {str(e)}")
                if "设置的时间不能是过去的时间" in str(e):
                    raise e
                raise ValueError("全连字符格式错误，请使用 YYYY-MM-DD-HH:MM 或 MM-DD-HH:MM 格式")
        
        # 尝试解析完整的年月日时分格式（无符号）如：202509170600
        if len(datetime_str) == 12 and datetime_str.isdigit():
            try:
                year = int(datetime_str[:4])
                month = int(datetime_str[4:6])
                day = int(datetime_str[6:8])
                hour = int(datetime_str[8:10])
                minute = int(datetime_str[10:12])
                
                # 验证日期时间有效性
                dt = datetime.datetime(year, month, day, hour, minute)
                
                # 检查时间是否在过去，如果是过去的年份则调整
                if dt.year < today.year:
                    dt = dt.replace(year=today.year)
                # 如果时间已过且不是当前时间（精确到分钟），调整为明年
                current_time_min = today.replace(second=0, microsecond=0)
                if dt < today and dt != current_time_min:
                    dt = dt.replace(year=today.year + 1)
                
                return dt.strftime("%Y-%m-%d %H:%M")
            except ValueError as e:
                if "设置的时间不能是过去的时间" in str(e):
                    raise e
                raise ValueError("完整时间格式错误，请使用 YYYYMMDDHHII 格式（如 202509170600）")
        
        # 尝试解析月份无符号格式（如：09170600）
        if len(datetime_str) == 8 and datetime_str.isdigit():
            try:
                month = int(datetime_str[:2])
                day = int(datetime_str[2:4])
                hour = int(datetime_str[4:6])
                minute = int(datetime_str[6:8])
                
                # 使用今年作为默认年份
                year = today.year
                dt = datetime.datetime(year, month, day, hour, minute)
                
                # 如果时间已过且不是当前时间（精确到分钟），使用明年
                current_time_min = today.replace(second=0, microsecond=0)
                if dt < today and dt != current_time_min:
                    dt = dt.replace(year=year + 1)
                
                return dt.strftime("%Y-%m-%d %H:%M")
            except ValueError as e:
                raise ValueError("月份时间格式错误，请使用 MMDDHHII 格式（如 09170600）")
        
        # 尝试解析带冒号的时间格式
        if ':' in datetime_str:
            # logger.info(f"尝试解析带冒号格式: '{datetime_str}'")
            parts = datetime_str.split(':')
            if len(parts) == 2:
                # HH:MM 格式
                try:
                    hour, minute = map(int, parts)
                    if not (0 <= hour <= 23 and 0 <= minute <= 59):
                        raise ValueError("时间超出范围")
                    
                    # 设置时间
                    dt = today.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    # 如果时间已过且不是当前时间（精确到分钟），设置为明天
                    current_time_min = today.replace(second=0, microsecond=0)
                    if dt < today and dt != current_time_min:
                        dt += datetime.timedelta(days=1)
                    
                    return dt.strftime("%Y-%m-%d %H:%M")
                except ValueError:
                    raise ValueError("时间格式错误，请使用 HH:MM 格式（如 8:05）")
            else:
                raise ValueError("时间格式错误，请使用 HH:MM 格式（如 8:05）")
        
        # 尝试解析无冒号的时间格式
        if len(datetime_str) == 4 and datetime_str.isdigit():
            try:
                hour = int(datetime_str[:2])
                minute = int(datetime_str[2:])
                
                if not (0 <= hour <= 23 and 0 <= minute <= 59):
                    raise ValueError("时间超出范围")
                
                # 设置时间
                dt = today.replace(hour=hour, minute=minute, second=0, microsecond=0)
                # 如果时间已过且不是当前时间（精确到分钟），设置为明天
                current_time_min = today.replace(second=0, microsecond=0)
                if dt < today and dt != current_time_min:
                    dt += datetime.timedelta(days=1)
                
                return dt.strftime("%Y-%m-%d %H:%M")
            except ValueError:
                raise ValueError("时间格式错误，请使用 HHMM 格式（如 0805）")
        
        # 如果都不匹配，抛出错误
        logger.error(f"parse_datetime 无法解析输入: '{original_input}' - 所有格式都不匹配")
        raise ValueError("时间格式错误，支持格式：HH:MM（如 8:05）、HHMM（如 0805）、YYYYMMDDHHII（如 202509170600）、YYYY-MM-DD-HH:MM（如 2025-09-17-06:00）、MM-DD-HH:MM（如 09-17-06:00）、MMDDHHII（如 09170600）")
        
    except Exception as e:
        if isinstance(e, ValueError):
            logger.error(f"parse_datetime 解析失败，输入: '{original_input}', 错误: {str(e)}")
            raise e
        logger.error(f"parse_datetime 发生未知错误，输入: '{original_input}', 错误: {str(e)}")
        raise ValueError("时间格式错误，支持格式：HH:MM（如 8:05）、HHMM（如 0805）、YYYYMMDDHHII（如 202509170600）、YYYY-MM-DD-HH:MM（如 2025-09-17-06:00）、MM-DD-HH:MM（如 09-17-06:00）、MMDDHHII（如 09170600）")

def is_outdated(reminder: dict) -> bool:
    '''检查提醒是否过期'''
    if "datetime" in reminder and reminder["datetime"]:  # 确保datetime存在且不为空
        try:
            return datetime.datetime.strptime(reminder["datetime"], "%Y-%m-%d %H:%M") < datetime.datetime.now()
        except ValueError:
            # 如果日期格式不正确，记录错误并返回False
            logger.error(f"提醒的日期时间格式错误: {reminder.get('datetime', '')}")
            return False
    return False

def load_reminder_data(data_file: str) -> dict:
    '''加载提醒数据'''
    if not os.path.exists(data_file):
        with open(data_file, "w", encoding='utf-8') as f:
            f.write("{}")
    with open(data_file, "r", encoding='utf-8') as f:
        return json.load(f)

async def save_reminder_data(data_file: str, reminder_data: dict):
    '''保存提醒数据'''
    # 在保存前清理过期的一次性任务和无效数据
    for group in list(reminder_data.keys()):
        reminder_data[group] = [
            r for r in reminder_data[group] 
            if "datetime" in r and r["datetime"] and  # 确保datetime字段存在且不为空
               not (r.get("repeat", "none") == "none" and is_outdated(r))
        ]
        # 如果群组没有任何提醒了，删除这个群组的条目
        if not reminder_data[group]:
            del reminder_data[group]
            
    with open(data_file, "w", encoding='utf-8') as f:
        json.dump(reminder_data, f, ensure_ascii=False)

def check_user_permission(user_id: str, whitelist: str) -> tuple:
    '''检查用户是否有权限使用插件
    
    Args:
        user_id: 用户ID
        whitelist: 白名单字符串，逗号分隔
        
    Returns:
        tuple: (是否有权限, 错误消息)
    '''
    # 如果白名单为空，则不限制
    if not whitelist or not whitelist.strip():
        return True, None
    
    # 处理中英文逗号分隔
    whitelist_clean = whitelist.replace('，', ',')  # 替换中文逗号为英文逗号
    allowed_users = [user.strip() for user in whitelist_clean.split(',') if user.strip()]
    
    if not allowed_users:
        return True, None
    
    if user_id in allowed_users:
        return True, None
    else:
        return False, "抱歉，您没有权限使用此插件功能。"

def check_permission_and_return_error(event, whitelist):
    '''检查权限并返回错误信息（如果有）
    
    Args:
        event: 事件对象
        whitelist: 白名单字符串
        
    Returns:
        str or None: 如果没有权限返回错误信息，否则返回None
    '''
    user_id = event.get_sender_id()
    has_permission, error_msg = check_user_permission(user_id, whitelist)
    return error_msg if not has_permission else None

def check_reminder_limit(reminder_data: dict, session_key: str, max_reminders_per_user: int, unique_session: bool, creator_id: str | None = None) -> tuple:
    '''检查提醒数量限制
    
    Args:
        reminder_data: 提醒数据字典
        session_key: 会话键
        max_reminders_per_user: 每用户最大提醒数量（0表示不限制）
        unique_session: 是否启用会话隔离
        creator_id: 创建者ID（用于会话隔离模式）
        
    Returns:
        tuple: (是否可以创建, 错误消息)
    '''
    if max_reminders_per_user <= 0:
        return True, None
    
    if unique_session:
        # 会话隔离模式：只计算当前用户在当前会话的提醒数量
        current_count = len(reminder_data.get(session_key, []))
        if current_count >= max_reminders_per_user:
            return False, f"提醒创建失败：已达到每用户最大提醒数量限制({max_reminders_per_user})。请删除一些旧提醒后再试。"
    else:
        # 全局模式：计算所有会话中的提醒总数
        total_count = sum(len(reminders) for reminders in reminder_data.values())
        if total_count >= max_reminders_per_user:
            return False, f"提醒创建失败：已达到全局最大提醒数量限制({max_reminders_per_user})。请删除一些旧提醒后再试。"
    
    return True, None

# 法定节假日相关功能
class HolidayManager:
    def __init__(self):
        # 数据文件路径处理 - 符合框架规范并保持向后兼容
        old_data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
        old_holiday_file = os.path.join(old_data_dir, "holiday_data", "holiday_cache.json")
        
        try:
            from astrbot.api.star import StarTools
            plugin_data_dir = StarTools.get_data_dir("ai_reminder")
            new_holiday_file = plugin_data_dir / "holiday_cache.json"
            
            # 检查旧位置是否存在节假日缓存文件
            if os.path.exists(old_holiday_file):
                # 旧位置有数据，执行数据迁移
                logger.info(f"检测到旧节假日缓存文件，开始数据迁移...")
                logger.info(f"旧位置: {old_holiday_file}")
                logger.info(f"新位置: {new_holiday_file}")
                
                # 确保新目录存在
                plugin_data_dir.mkdir(parents=True, exist_ok=True)
                
                # 迁移节假日缓存文件
                import shutil
                try:
                    # 复制文件到新位置
                    shutil.copy2(old_holiday_file, new_holiday_file)
                    logger.info(f"节假日缓存迁移成功: {old_holiday_file} -> {new_holiday_file}")
                    
                    # 删除旧文件
                    os.remove(old_holiday_file)
                    logger.info(f"旧节假日缓存文件已删除: {old_holiday_file}")
                    
                    # 使用新位置
                    self.holiday_cache_file = new_holiday_file
                    logger.info(f"使用新的框架规范节假日缓存目录: {self.holiday_cache_file}")
                    
                except Exception as e:
                    logger.error(f"节假日缓存迁移失败: {e}")
                    # 迁移失败，继续使用旧位置
                    self.holiday_cache_file = old_holiday_file
                    logger.info(f"迁移失败，继续使用旧节假日缓存目录: {self.holiday_cache_file}")
            else:
                # 旧位置没有数据，直接使用新位置
                self.holiday_cache_file = new_holiday_file
                logger.info(f"使用框架规范节假日缓存目录: {self.holiday_cache_file}")
                
        except Exception as e:
            # 如果框架方法失败，回退到旧的数据目录
            os.makedirs(os.path.join(old_data_dir, "holiday_data"), exist_ok=True)
            self.holiday_cache_file = old_holiday_file
            logger.info(f"回退到兼容节假日缓存目录: {self.holiday_cache_file}")
            logger.warning(f"框架数据目录获取失败: {e}")
        
        self.holiday_data = self._load_holiday_data()
        
    def _load_holiday_data(self) -> dict:
        """加载节假日数据缓存"""
        if not os.path.exists(self.holiday_cache_file):
            return {}
        
        try:
            with open(self.holiday_cache_file, "r", encoding='utf-8') as f:
                data = json.load(f)
                
            # 检查数据是否过期（缓存超过30天更新一次）
            if "last_update" in data:
                last_update = datetime.datetime.fromisoformat(data["last_update"])
                now = datetime.datetime.now()
                if (now - last_update).days > 30:
                    logger.info("节假日数据缓存已过期，需要更新")
                    return {}
                    
            return data
        except Exception as e:
            logger.error(f"加载节假日数据缓存失败: {e}")
            return {}
    
    async def _save_holiday_data(self):
        """保存节假日数据缓存"""
        try:
            # 添加最后更新时间
            self.holiday_data["last_update"] = datetime.datetime.now().isoformat()
            
            with open(self.holiday_cache_file, "w", encoding='utf-8') as f:
                json.dump(self.holiday_data, f, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存节假日数据缓存失败: {e}")
            
    async def fetch_holiday_data(self, year: int | None = None) -> dict:
        """获取指定年份的节假日数据
        
        Args:
            year: 年份，默认为当前年份
            
        Returns:
            dict: 节假日数据，格式为 {日期字符串: 布尔值}
                  布尔值说明: True-法定节假日, False-调休工作日（需要补班的周末）
        """
        if year is None:
            year = datetime.datetime.now().year
            
        # 如果缓存中已有数据则直接返回
        year_key = str(year)
        if year_key in self.holiday_data and "data" in self.holiday_data[year_key]:
            return self.holiday_data[year_key]["data"]
            
        # 否则从API获取
        try:
            # 使用 http://timor.tech/api/holiday/year/{year} 接口获取数据
            url = f"http://timor.tech/api/holiday/year/{year}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"获取节假日数据失败，状态码: {response.status}")
                        return {}
                        
                    json_data = await response.json()
                    
                    if json_data.get("code") != 0:
                        logger.error(f"获取节假日数据失败: {json_data.get('msg')}")
                        return {}
                    
                    holiday_data = {}
                    for date_str, info in json_data.get("holiday", {}).items():
                        holiday_data[date_str] = info.get("holiday")
                    
                    # 缓存数据
                    if year_key not in self.holiday_data:
                        self.holiday_data[year_key] = {}
                    self.holiday_data[year_key]["data"] = holiday_data
                    await self._save_holiday_data()
                    
                    return holiday_data
        except Exception as e:
            logger.error(f"获取节假日数据出错: {e}")
            return {}
    
    async def is_holiday(self, date: datetime.datetime | None = None) -> bool:
        """判断指定日期是否为法定节假日
        
        Args:
            date: 日期，默认为当天
            
        Returns:
            bool: 是否为法定节假日
        """
        if date is None:
            date = datetime.datetime.now()
            
        year = date.year
        # 获取完整日期和不含年份的日期
        full_date_str = date.strftime("%Y-%m-%d")
        short_date_str = date.strftime("%m-%d")
        
        # 获取该年份的节假日数据
        holiday_data = await self.fetch_holiday_data(year)
        
        # 判断是否在节假日数据中，使用不含年份的短日期格式
        if short_date_str in holiday_data:
            # 如果值为True，表示法定节假日
            is_holiday = holiday_data[short_date_str] == True
            return is_holiday
            
        # 如果不在特殊日期列表中，则根据是否为周末判断
        if date.weekday() >= 5:  # 5和6分别是周六和周日
            return True
            
        return False
    
    async def is_workday(self, date: datetime.datetime | None = None) -> bool:
        """判断指定日期是否为工作日
        
        Args:
            date: 日期，默认为当天
            
        Returns:
            bool: 是否为工作日
        """
        if date is None:
            date = datetime.datetime.now()
            
        year = date.year
        # 获取完整日期和不含年份的日期
        full_date_str = date.strftime("%Y-%m-%d")
        short_date_str = date.strftime("%m-%d")
        
        # 获取该年份的节假日数据
        holiday_data = await self.fetch_holiday_data(year)
        
        # 判断是否在节假日数据中，使用不含年份的短日期格式
        if short_date_str in holiday_data:
            # 如果值为False，表示调休工作日（需要补班的周末）
            # 如果值为True，表示法定节假日
            is_workday = holiday_data[short_date_str] == False
            return is_workday
            
        # 如果是周末且不在节假日数据中，则不是工作日
        if date.weekday() >= 5:  # 5和6分别是周六和周日
            return False
            
        return True 

# v3/v4兼容性处理功能
def normalize_unified_msg_origin(unified_msg_origin):
    """标准化unified_msg_origin格式，处理v3/v4兼容性
    
    Args:
        unified_msg_origin: 原始的统一消息来源字符串
        
    Returns:
        str: 标准化后的统一消息来源字符串
    """
    if not unified_msg_origin or ":" not in unified_msg_origin:
        return unified_msg_origin
    
    parts = unified_msg_origin.split(":", 2)
    if len(parts) < 3:
        return unified_msg_origin
    
    platform_part, message_type, session_id = parts
    
    # 检测v3格式的平台名称（不包含下划线的常见平台名）
    v3_platform_names = [
        "aiocqhttp", "qq_official", "discord", "slack", "telegram", 
        "wechatmp", "wechatferry", "wecom", "weixin_official_account",
        "satori", "webchat"
    ]
    
    # 如果是v3格式的平台名称，保持不变
    if platform_part in v3_platform_names:
        return unified_msg_origin
    
    # 如果是v4格式（可能包含实例ID），尝试提取平台类型
    for platform_name in v3_platform_names:
        if platform_part.startswith(platform_name):
            # 这可能是v4格式，为了向后兼容，我们保持原格式
            # 但要确保数据能被正确处理
            return unified_msg_origin
    
    return unified_msg_origin

def get_platform_type_from_origin(unified_msg_origin, context=None):
    """从unified_msg_origin中提取平台类型
    
    注意：这个函数只用于判断平台类型，不应该用于构建新的origin
    对于v4格式（如 aiocqhttp-123），会返回基础平台类型（aiocqhttp）
    
    Args:
        unified_msg_origin: 统一消息来源字符串
        context: AstrBot上下文对象，用于获取平台实例（可选）
        
    Returns:
        str: 平台类型名称 (如 aiocqhttp, discord 等)
    """
    if not unified_msg_origin or ":" not in unified_msg_origin:
        return "unknown"
    
    platform_part = unified_msg_origin.split(":", 1)[0]
    
    # 如果有context，尝试通过平台管理器获取真实的适配器类型
    if context:
        try:
            platform_inst = context.get_platform_inst(platform_part)
            if platform_inst:
                return platform_inst.meta().name
        except Exception as e:
            logger.warning(f"通过context获取平台类型失败: {e}")
    
    # v3格式的平台名称
    v3_platform_names = [
        "aiocqhttp", "qq_official", "discord", "slack", "telegram", 
        "wechatmp", "wechatferry", "wecom", "weixin_official_account",
        "satori", "webchat"
    ]
    
    # 直接匹配v3平台名称
    if platform_part in v3_platform_names:
        return platform_part
    
    # 尝试从v4格式中提取平台类型
    for platform_name in v3_platform_names:
        if platform_part.startswith(platform_name):
            return platform_name
    
    return platform_part

def get_platform_id_from_origin(unified_msg_origin):
    """从unified_msg_origin中提取平台ID（原始的第一部分）
    
    这个函数用于获取原始的platform_id，无论是v3还是v4格式
    
    Args:
        unified_msg_origin: 统一消息来源字符串
        
    Returns:
        str: 平台ID (如 aiocqhttp, aiocqhttp-123, 本地 等)
    """
    if not unified_msg_origin or ":" not in unified_msg_origin:
        return "unknown"
    
    return unified_msg_origin.split(":", 1)[0]

def get_platform_type_from_system(platform_id, context=None):
    """从系统中获取platform_id对应的真实平台类型
    
    这个函数通过查询系统中注册的平台实例来获取真实的平台类型
    
    Args:
        platform_id: 平台ID
        context: AstrBot的Context对象（如果有的话）
        
    Returns:
        str: 真实的平台类型，如果找不到则返回platform_id本身
    """
    if not context:
        # 如果没有context，尝试从全局获取
        try:
            from astrbot.core.star import star_map
            if star_map:
                # 取第一个可用的context
                context = next(iter(star_map.values()), None)
        except:
            pass
    
    if context and hasattr(context, 'get_platform_inst'):
        try:
            platform_inst = context.get_platform_inst(platform_id)
            if platform_inst:
                return platform_inst.meta().name
        except Exception as e:
            logger.warning(f"从系统获取平台类型失败: {e}")
    
    # 如果无法从系统获取，回退到基于字符串的判断
    return get_platform_type_from_origin(f"{platform_id}:dummy:dummy")

def is_compatible_platform_origin(origin1, origin2):
    """检查两个unified_msg_origin是否指向同一个实际会话
    
    这个函数用于处理v3/v4兼容性，判断两个不同格式的origin是否实际指向同一个会话
    
    Args:
        origin1: 第一个统一消息来源字符串
        origin2: 第二个统一消息来源字符串
        
    Returns:
        bool: 如果指向同一个会话返回True
    """
    if origin1 == origin2:
        return True
    
    # 解析两个origin
    parts1 = origin1.split(":", 2) if origin1 and ":" in origin1 else []
    parts2 = origin2.split(":", 2) if origin2 and ":" in origin2 else []
    
    if len(parts1) < 3 or len(parts2) < 3:
        return False
    
    platform1, msg_type1, session1 = parts1
    platform2, msg_type2, session2 = parts2
    
    # 消息类型和会话ID必须相同
    if msg_type1 != msg_type2 or session1 != session2:
        return False
    
    # 检查平台是否兼容（支持双向匹配）
    platform_id1 = get_platform_id_from_origin(origin1)
    platform_id2 = get_platform_id_from_origin(origin2)
    
    # 如果platform_id完全相同，直接匹配
    if platform_id1 == platform_id2:
        return True
    
    # 获取平台类型进行兼容性匹配（优先使用系统查询）
    platform_type1 = get_platform_type_from_system(platform_id1, None)
    platform_type2 = get_platform_type_from_system(platform_id2, None)
    
    # 如果系统查询失败，回退到字符串分析
    if platform_type1 == platform_id1:
        platform_type1 = get_platform_type_from_origin(origin1)
    if platform_type2 == platform_id2:
        platform_type2 = get_platform_type_from_origin(origin2)
    
    # 平台类型必须相同才能兼容
    if platform_type1 != platform_type2:
        return False
    
    # v3格式的平台名称列表
    v3_platform_names = [
        "aiocqhttp", "qq_official", "discord", "slack", "telegram", 
        "wechatmp", "wechatferry", "wecom", "weixin_official_account",
        "satori", "webchat"
    ]
    
    # 如果都是v3格式，必须完全匹配
    if platform_id1 in v3_platform_names and platform_id2 in v3_platform_names:
        return platform_id1 == platform_id2
    
    # 如果一个是v3格式，一个是v4格式（或者都是v4但不同实例），则通过平台类型匹配
    return True

def find_compatible_reminder_key(reminder_data, target_origin, compatibility_handler=None):
    """在提醒数据中查找与目标origin兼容的key
    
    Args:
        reminder_data: 提醒数据字典
        target_origin: 目标统一消息来源字符串
        compatibility_handler: 可选的兼容性处理器，用于更精确的匹配
        
    Returns:
        str or None: 找到的兼容key，如果没找到返回None
    """
    # 首先尝试直接匹配
    if target_origin in reminder_data:
        return target_origin
    
    # 然后尝试兼容性匹配
    for existing_key in reminder_data.keys():
        if compatibility_handler:
            # 使用兼容性处理器的精确匹配
            is_compatible = compatibility_handler.is_compatible_origin(existing_key, target_origin)
        else:
            # 回退到原始的兼容性匹配
            is_compatible = is_compatible_platform_origin(existing_key, target_origin)
            
        if is_compatible:
            logger.info(f"找到兼容的提醒数据key: {existing_key} <-> {target_origin}")
            return existing_key
    
    return None

# 兼容性处理类
class CompatibilityHandler:
    """处理v3/v4兼容性的工具类"""
    
    def __init__(self, reminder_data, context=None):
        self.reminder_data = reminder_data
        self.context = context
    
    def get_reminders(self, unified_msg_origin):
        """获取指定origin的提醒列表，支持兼容性查找"""
        # 首先尝试直接获取
        if unified_msg_origin in self.reminder_data:
            return self.reminder_data[unified_msg_origin]
        
        # 尝试兼容性查找（使用自己的精确匹配）
        compatible_key = find_compatible_reminder_key(self.reminder_data, unified_msg_origin, self)
        if compatible_key:
            return self.reminder_data[compatible_key]
        
        return []
    
    def ensure_key_exists(self, unified_msg_origin):
        """确保指定的key存在，如果不存在则创建或使用兼容的key
        
        Returns:
            str: 实际使用的key
        """
        # 检查是否有兼容的key存在（使用自己的精确匹配）
        compatible_key = find_compatible_reminder_key(self.reminder_data, unified_msg_origin, self)
        
        if compatible_key:
            # 使用现有的兼容key
            target_key = compatible_key
        else:
            # 使用新的key
            target_key = unified_msg_origin
        
        if target_key not in self.reminder_data:
            self.reminder_data[target_key] = []
        
        return target_key
    
    def add_reminder(self, unified_msg_origin, reminder_item):
        """添加提醒，使用兼容性处理"""
        target_key = self.ensure_key_exists(unified_msg_origin)
        self.reminder_data[target_key].append(reminder_item)
        return target_key
    
    def remove_reminder(self, unified_msg_origin, index):
        """删除提醒，使用兼容性处理"""
        compatible_key = find_compatible_reminder_key(self.reminder_data, unified_msg_origin, self)
        
        if not compatible_key:
            return None, "没有找到对应的提醒数据"
        
        reminders = self.reminder_data[compatible_key]
        if index < 0 or index >= len(reminders):
            return None, "序号无效"
        
        removed_item = reminders.pop(index)
        return removed_item, compatible_key
    
    def get_actual_key(self, unified_msg_origin):
        """获取实际使用的key"""
        return find_compatible_reminder_key(self.reminder_data, unified_msg_origin, self) or unified_msg_origin
    
    def is_compatible_origin(self, origin1, origin2):
        """使用context检查两个origin是否兼容"""
        if origin1 == origin2:
            return True
        
        # 解析两个origin
        parts1 = origin1.split(":", 2) if origin1 and ":" in origin1 else []
        parts2 = origin2.split(":", 2) if origin2 and ":" in origin2 else []
        
        if len(parts1) < 3 or len(parts2) < 3:
            return False
        
        platform1, msg_type1, session1 = parts1
        platform2, msg_type2, session2 = parts2
        
        # 消息类型和会话ID必须相同
        if msg_type1 != msg_type2 or session1 != session2:
            return False
        
        # 如果platform_id完全相同，直接匹配
        if platform1 == platform2:
            return True
        
        # 使用系统查询获取真实的平台类型
        platform_type1 = get_platform_type_from_system(platform1, self.context)
        platform_type2 = get_platform_type_from_system(platform2, self.context)
        
        # 如果系统查询失败，回退到字符串分析
        if platform_type1 == platform1:
            platform_type1 = get_platform_type_from_origin(origin1)
        if platform_type2 == platform2:
            platform_type2 = get_platform_type_from_origin(origin2)
        
        # 平台类型必须相同才能兼容
        if platform_type1 != platform_type2:
            return False
        
        # v3格式的平台名称列表
        v3_platform_names = [
            "aiocqhttp", "qq_official", "discord", "slack", "telegram", 
            "wechatmp", "wechatferry", "wecom", "weixin_official_account",
            "satori", "webchat"
        ]
        
        # 如果都是v3格式，必须完全匹配
        if platform1 in v3_platform_names and platform2 in v3_platform_names:
            return platform1 == platform2
        
        # 如果一个是v3格式，一个是v4格式（或者都是v4但不同实例），则通过平台类型匹配
        return True 