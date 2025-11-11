import datetime
import json
import random
from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import At, Plain
from astrbot.api.platform import AstrBotMessage, PlatformMetadata, MessageType, MessageMember
from astrbot.core.platform.astr_message_event import AstrMessageEvent, MessageSesion
from .utils import get_platform_type_from_origin, get_platform_id_from_origin


class ReminderMessageHandler:
    """处理提醒消息的发送和格式化"""
    
    def __init__(self, context, wechat_platforms, config=None):
        self.context = context
        self.wechat_platforms = wechat_platforms
        self.config = config or {}
    
    def _add_at_message(self, msg_chain, original_msg_origin, reminder):
        """添加@消息的helper函数"""
        platform_type = get_platform_type_from_origin(original_msg_origin, self.context)
        logger.info(f"@消息调试 - 平台类型: {platform_type}, original_msg_origin: {original_msg_origin}")
        if platform_type == "aiocqhttp":
            # QQ平台 - 优先使用昵称，回退到ID
            if "creator_name" in reminder and reminder["creator_name"]:
                msg_chain.chain.append(At(qq=reminder["creator_id"], name=reminder["creator_name"]))
            else:
                msg_chain.chain.append(At(qq=reminder["creator_id"]))
        elif platform_type in self.wechat_platforms:
            if "creator_name" in reminder and reminder["creator_name"]:
                msg_chain.chain.append(Plain(f"@{reminder['creator_name']} "))
            else:
                msg_chain.chain.append(Plain(f"@{reminder['creator_id']} "))
        else:
            msg_chain.chain.append(Plain(f"@{reminder['creator_id']} "))
    
    def is_private_chat(self, unified_msg_origin: str) -> bool:
        """判断是否为私聊"""
        return ":FriendMessage:" in unified_msg_origin
    
    def is_group_chat(self, unified_msg_origin: str) -> bool:
        """判断是否为群聊"""
        return (":GroupMessage:" in unified_msg_origin) or ("@chatroom" in unified_msg_origin)
    
    def get_original_session_id(self, session_id: str) -> str:
        """从隔离格式的会话ID中提取原始会话ID，用于消息发送"""
        # 检查是否是微信平台
        platform_type = get_platform_type_from_origin(session_id, self.context)
        is_wechat_platform = platform_type in self.wechat_platforms
        
        # 处理微信群聊的特殊情况
        if "@chatroom" in session_id:
            # 微信群聊ID可能有两种格式:
            # 1. platform:GroupMessage:12345678@chatroom_wxid_abc123 (带用户隔离)
            # 2. platform:GroupMessage:12345678@chatroom (原始格式)
            
            # 提取平台前缀
            platform_prefix = ""
            if ":" in session_id:
                parts = session_id.split(":", 2)
                if len(parts) >= 2:
                    platform_prefix = f"{parts[0]}:{parts[1]}:"
            
            # 然后处理@chatroom后面的部分
            chatroom_parts = session_id.split("@chatroom")
            if len(chatroom_parts) == 2:
                if chatroom_parts[1].startswith("_"):
                    # 如果有下划线，说明这是带用户隔离的格式
                    room_id = chatroom_parts[0].split(":")[-1]
                    return f"{platform_prefix}{room_id}@chatroom"
                else:
                    # 这已经是原始格式，直接返回
                    return session_id
        
        # 处理其他平台的情况
        if "_" in session_id and ":" in session_id:
            # 首先判断是否是微信相关平台
            if is_wechat_platform:
                # 微信平台需要特殊处理
                # 因为微信个人ID通常包含下划线，不适合用通用分割方法
                
                # 但是，如果明确是群聊隔离格式，仍然需要处理
                if "@chatroom_" in session_id:
                    # 这部分已经在上面处理过了
                    pass
                elif ":GroupMessage:" in session_id and "_" in session_id.split(":")[-1]:
                    # 可能是其他格式的群聊隔离
                    parts = session_id.split(":")
                    if len(parts) >= 3:
                        group_parts = parts[-1].rsplit("_", 1)
                        if len(group_parts) == 2:
                            return f"{parts[0]}:{parts[1]}:{group_parts[0]}"
                
                # 如果没有命中上述规则，返回原始ID
                return session_id
            elif platform_type == "lark":
                return session_id
            else:
                # 非微信平台，使用通用规则
                parts = session_id.rsplit(":", 1)
                if len(parts) == 2 and "_" in parts[1]:
                    # 查找最后一个下划线，认为这是会话隔离添加的
                    group_id, user_id = parts[1].rsplit("_", 1)
                    return f"{parts[0]}:{group_id}"
        
        # 如果不是隔离格式或无法解析，返回原始ID
        return session_id
    
    def create_at_message(self, reminder: dict, original_msg_origin: str, is_task: bool = False, is_command_task: bool = False) -> MessageChain:
        """创建@消息"""
        msg = MessageChain()
        
        # 根据配置决定是否添加@
        should_at = False
        if is_command_task:
            should_at = self.config.get("enable_command_at", False)
        elif is_task:
            should_at = self.config.get("enable_task_at", True)
        else:
            should_at = self.config.get("enable_reminder_at", True)
        
        if should_at and not self.is_private_chat(original_msg_origin) and "creator_id" in reminder and reminder["creator_id"]:
            platform_type = get_platform_type_from_origin(original_msg_origin, self.context)
            if platform_type == "aiocqhttp":
                # QQ平台 - 优先使用昵称，回退到ID
                if "creator_name" in reminder and reminder["creator_name"]:
                    msg.chain.append(At(qq=reminder["creator_id"], name=reminder["creator_name"]))
                else:
                    msg.chain.append(At(qq=reminder["creator_id"]))
            elif platform_type in self.wechat_platforms:
                # 所有微信平台 - 使用用户名/昵称而不是ID
                if "creator_name" in reminder and reminder["creator_name"]:
                    msg.chain.append(Plain(f"@{reminder['creator_name']} "))
                else:
                    # 如果没有保存用户名，尝试使用ID
                    msg.chain.append(Plain(f"@{reminder['creator_id']} "))
            else:
                # 其他平台的@实现
                msg.chain.append(Plain(f"@{reminder['creator_id']} "))
        
        return msg
    
    async def send_reminder_message(self, unified_msg_origin: str, reminder: dict, content: str, is_task: bool = False, is_command_task: bool = False):
        """发送提醒消息"""
        original_msg_origin = self.get_original_session_id(unified_msg_origin)
        
        # 构建消息链
        msg = self.create_at_message(reminder, original_msg_origin, is_task, is_command_task)
        
        # 添加内容
        if is_task:
            msg.chain.append(Plain(content))
        else:
            msg.chain.append(Plain("[提醒] " + content))
        
        logger.info(f"尝试发送{'指令任务' if is_command_task else '任务' if is_task else '提醒'}消息到: {original_msg_origin} (原始ID: {unified_msg_origin})")
        send_result = await self.context.send_message(original_msg_origin, msg)
        logger.info(f"消息发送结果: {send_result}")
        
        return send_result


class TaskExecutor:
    """处理任务执行相关的功能"""
    
    def __init__(self, context, wechat_platforms, config=None):
        self.context = context
        self.wechat_platforms = wechat_platforms
        self.config = config or {}
        self.message_handler = ReminderMessageHandler(context, wechat_platforms, config)
    
    def _apply_safe_session_parser(self):
        """应用安全的会话解析器补丁"""
        try:
            original_from_str = MessageSesion.from_str
            
            # 修复：移除 @classmethod 并修正签名
            def safe_from_str(session_str):
                try:
                    # 先尝试原始方法
                    return original_from_str(session_str)
                except Exception as e:
                    # 如果正常解析失败，创建一个默认的MessageSesion
                    logger.warning(f"安全解析session失败：{str(e)}，使用安全模式")
                    
                    # 特殊处理含多个冒号的情况
                    if session_str.count(":") >= 2:
                        # 正确分割，避免 "too many values to unpack" 错误
                        parts = session_str.split(":")
                        platform = parts[0]
                        
                        # 智能判断消息类型
                        msg_type_str = "FriendMessage"
                        if "FriendMessage" in session_str:
                            msg_type_str = "FriendMessage"
                        elif "GroupMessage" in session_str:
                            msg_type_str = "GroupMessage"
                        else:
                            msg_type_str = parts[1] if len(parts) > 1 else "FriendMessage"
                            
                        # 将剩余部分重新组合作为session_id
                        session_id = ":".join(parts[2:]) if len(parts) > 2 else "unknown"
                    else:
                        # 处理简单情况
                        parts = session_str.split(":", 1)
                        platform = parts[0] if parts else "unknown"
                        msg_type_str = "FriendMessage"  # 默认为私聊
                        session_id = parts[1] if len(parts) > 1 else session_str
                    
                    # 尝试创建MessageSesion对象
                    try:
                        # 修复：使用 MessageType 枚举
                        message_type = MessageType.FRIEND_MESSAGE if msg_type_str == "FriendMessage" else MessageType.GROUP_MESSAGE
                        return MessageSesion(platform, message_type, session_id)
                    except Exception as inner_e:
                        logger.error(f"创建安全MessageSesion失败: {str(inner_e)}")
                        # 如果还是失败，返回一个硬编码的对象
                        return MessageSesion("unknown", MessageType.FRIEND_MESSAGE, "unknown")
            
            # 应用猴子补丁
            if hasattr(MessageSesion, "from_str"):
                MessageSesion.from_str = safe_from_str
                logger.info("已应用MessageSesion安全解析补丁")
                
        except Exception as e:
            logger.error(f"设置安全解析器失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _create_platform_helper(self, send_session_id: str):
        """创建平台辅助工具"""
        class PlatformHelperWithSend:
            def __init__(self, context, session_id):
                self.context = context
                self.session_id = session_id
                
            async def send_message(self, message):
                try:
                    return await self.context.send_message(self.session_id, message)
                except Exception as e:
                    logger.error(f"平台工具发送消息失败: {str(e)}")
                    return False
        
        return PlatformHelperWithSend(self.context, send_session_id)
    
    def _ensure_event_attributes(self, event, send_session_id: str, reminder: dict, is_private_chat: bool, platform_name: str):
        """确保事件对象具有所有可能需要的属性"""
        # 添加常用的reply方法
        if not hasattr(event, "reply"):
            async def reply_func(content):
                # 这个属性现在不再用于控制流程，但为了兼容可能依赖它的旧函数，暂时保留
                setattr(event, '_has_send_oper', True)
                msg_chain = MessageChain()
                if isinstance(content, str):
                    msg_chain.chain.append(Plain(content))
                else:
                    msg_chain = content
                return await self.context.send_message(send_session_id, msg_chain)
            event.reply = reply_func
        
        # 添加session_id属性
        if not hasattr(event, "session_id"):
            event.session_id = send_session_id
        
        # 添加get_session_id方法
        if not hasattr(event, "get_session_id"):
            event.get_session_id = lambda: send_session_id
        
        # 添加get_platform_type方法
        if not hasattr(event, "get_platform_type"):
            event.get_platform_type = lambda: platform_name
        
        # 添加get_message_type方法
        if not hasattr(event, "get_message_type"):
            msg_type = "friend" if is_private_chat else "group"
            event.get_message_type = lambda: msg_type
        
        # 添加get_sender_id方法（如果还没有）
        if hasattr(event, "get_sender_id"):
            original_get_sender = event.get_sender_id
            def safe_get_sender():
                try:
                    return original_get_sender()
                except:
                    return reminder.get("creator_id", "unknown")
            event.get_sender_id = safe_get_sender
        else:
            # 确保返回的是字符串类型的ID
            def get_sender_id():
                sender_id = reminder.get("creator_id", "unknown")
                return str(sender_id) if sender_id else "unknown"
            event.get_sender_id = get_sender_id

        # 设置 sender 身份
        creator_id = str(reminder.get("creator_id"))
        admin_ids = self.context._config.get("admins_id", [])
        if creator_id and creator_id in admin_ids:
            event.role = "admin"
        else:
            event.role = "member"

        # 添加结果管理方法，支持复杂消息类型
        if not hasattr(event, '_result'):
            from astrbot.core.message.message_event_result import MessageEventResult
            event._result = MessageEventResult()
        
        if not hasattr(event, 'get_result'):
            def get_result():
                return event._result
            event.get_result = get_result
        
        if not hasattr(event, 'set_result'):
            def set_result(result):
                if hasattr(result, 'chain'):
                    event._result = result
                else:
                    # 如果是字符串，转换为MessageEventResult
                    from astrbot.core.message.message_event_result import MessageEventResult
                    from astrbot.core.message.components import Plain
                    msg_result = MessageEventResult()
                    msg_result.chain.append(Plain(str(result)))
                    event._result = msg_result
            event.set_result = set_result
    
    def _create_event_object(self, task_text: str, unified_msg_origin: str, reminder: dict, is_private_chat: bool, send_session_id: str):
        """创建事件对象"""
        msg = AstrBotMessage()
        msg.message_str = task_text
        msg.session_id = send_session_id
        msg.type = MessageType.FRIEND_MESSAGE if is_private_chat else MessageType.GROUP_MESSAGE
        msg.self_id = "astrbot_reminder"
        
        from astrbot.core.message.components import Plain
        msg.message = [Plain(task_text)]
        
        if "creator_id" in reminder:
            msg.sender = MessageMember(reminder["creator_id"], reminder.get("creator_name", "用户"))
        else:
            msg.sender = MessageMember("unknown", "用户")
        
        if not is_private_chat:
            if ":" in send_session_id:
                parts = send_session_id.split(":")
                if len(parts) >= 3:
                    group_id_part = parts[2]
                    if "_" in group_id_part:
                        group_id_part = group_id_part.split("_")[0]
                    msg.group_id = group_id_part
                else:
                    msg.group_id = "unknown"
            else:
                msg.group_id = "unknown"
        
        platform_name = get_platform_type_from_origin(unified_msg_origin, self.context)
        platform_id = get_platform_id_from_origin(unified_msg_origin)

        raw_session_id = send_session_id
        if ":" in send_session_id:
            parts = send_session_id.split(":")
            if len(parts) >= 3:
                raw_session_id = parts[2]
            else:
                raw_session_id = send_session_id
        
        meta = PlatformMetadata(platform_name, "scheduler", platform_id)
        event = AstrMessageEvent(
            message_str=task_text,
            message_obj=msg,
            platform_meta=meta,
            session_id=raw_session_id
        )
        
        # 使用 setattr 动态添加属性以绕过静态检查
        setattr(event, '_send_session_id', send_session_id)
        setattr(event, '_has_send_oper', False)
        
        if not hasattr(event.message_obj, "platform"):
            setattr(event.message_obj, 'platform', self._create_platform_helper(send_session_id))
        
        self._ensure_event_attributes(event, send_session_id, reminder, is_private_chat, platform_name)
        
        return event
    
    # 修复：恢复被误删的 _get_send_session_id 方法
    def _get_send_session_id(self, unified_msg_origin: str, is_private_chat: bool) -> str:
        """获取用于发送消息的、格式完整的会话ID"""
        send_session_id = self.message_handler.get_original_session_id(unified_msg_origin)
        
        if ":" in send_session_id:
            return send_session_id
        else:
            platform_name = get_platform_type_from_origin(unified_msg_origin, self.context)
            msg_type_str = "FriendMessage" if is_private_chat else "GroupMessage"
            return f"{platform_name}:{msg_type_str}:{send_session_id}"

    async def execute_task(self, unified_msg_origin: str, reminder: dict, provider, func_tool):
        """【重构】执行任务"""
        task_text = reminder['text']
        logger.info(f"Task Activated: {task_text}, attempting to execute for {unified_msg_origin}")
        
        self._apply_safe_session_parser()
        
        enable_context = self.config.get("enable_context", True)
        max_context_count = self.config.get("max_context_count", 5)
        
        # 修复：在 try 块外初始化 original_msg_origin
        original_msg_origin = self.message_handler.get_original_session_id(unified_msg_origin)

        try:
            # 1. 获取对话上下文和预设人设
            curr_cid = None
            conversation = None
            contexts = []
            system_prompt = ""

            # 从 PersonaManager 获取预设人设
            try:
                persona = await self.context.persona_manager.get_default_persona_v3(umo=unified_msg_origin)
                system_prompt = persona["prompt"]
                logger.info(f"成功获取会话人设: {persona['name']}")
            except Exception as e:
                logger.error(f"获取会话人设失败，将使用默认值: {e}")
                system_prompt = "You are a helpful assistant."

            if enable_context:
                curr_cid = await self.context.conversation_manager.get_curr_conversation_id(original_msg_origin)
                if curr_cid:
                    conversation = await self.context.conversation_manager.get_conversation(original_msg_origin, curr_cid)
                    if conversation:
                        history_json = conversation.history or "[]"
                        contexts = json.loads(history_json)
                        logger.info(f"任务模式：找到用户对话，对话ID: {curr_cid}, 上下文长度: {len(contexts)}")
                
                if not curr_cid or not conversation:
                    curr_cid = await self.context.conversation_manager.new_conversation(original_msg_origin)
                    logger.info(f"创建新对话，对话ID: {curr_cid}")

            # 2. 构造初始Prompt
            prompt = f"请执行以下任务：{task_text}。请直接执行，不要提及这是一个预设任务。"
            if task_text.startswith("请调用") and "函数" in task_text:
                prompt = f"用户请求你执行以下操作：{task_text}。请直接执行这个任务，不要解释你在做什么，就像用户刚刚发出这个请求一样。"
            
            # 3. 首次调用LLM
            logger.info(f"首次调用LLM: {prompt[:100]}...")
            
            first_call_history = contexts.copy()
            first_call_history.append({"role": "user", "content": task_text})

            response = await provider.text_chat(
                prompt=prompt,
                session_id=unified_msg_origin,
                contexts=first_call_history,
                func_tool=func_tool,
                system_prompt=system_prompt
            )
            
            logger.info(f"LLM首次响应类型: {response.role}")
            
            final_reply_text = ""
            
            # 4. 根据LLM的首次响应进行处理
            if response.role == "tool" and hasattr(response, 'tools_call_name') and response.tools_call_name:
                # 场景：LLM决定调用工具
                tool_results = await self._handle_tool_calls(response, func_tool, task_text, unified_msg_origin, reminder)
                
                final_reply_text = await self._summarize_tool_results(
                    tool_results=tool_results, 
                    task_text=task_text, 
                    unified_msg_origin=unified_msg_origin, 
                    provider=provider, 
                    system_prompt=system_prompt
                )

            elif response.role == "assistant" and response.completion_text:
                # 场景：LLM直接返回文本回复
                final_reply_text = response.completion_text
            else:
                # 场景：未知或空回复
                final_reply_text = "任务执行完成，但未返回明确结果。"

            # 5. 统一发送结果汇报
            result_msg = MessageChain([Plain(final_reply_text)])
            await self._send_task_result(unified_msg_origin, reminder, result_msg)
            
            # 6. 统一更新对话历史
            if enable_context and curr_cid:
                history_to_save = contexts.copy()
                history_to_save.append({"role": "user", "content": task_text})
                history_to_save.append({"role": "assistant", "content": final_reply_text})
                await self._update_conversation_history(original_msg_origin, curr_cid, history_to_save)
            
            logger.info(f"Task executed successfully: {task_text}")
            
        except Exception as e:
            logger.error(f"执行任务时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            await self.context.send_message(original_msg_origin, f"执行任务时出错: {str(e)}")

    
    async def _execute_command_task(self, unified_msg_origin: str, reminder: dict, command: str):
        """执行指令任务"""
        try:
            from .command_trigger import CommandTrigger
            trigger = CommandTrigger(self.context, self.wechat_platforms, self.config)
            await trigger.trigger_and_forward_command(unified_msg_origin, reminder, command)
        except Exception as e:
            logger.error(f"执行指令任务时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            await self.context.send_message(
                self.message_handler.get_original_session_id(unified_msg_origin),
                f"执行指令任务 /{command} 时出错: {str(e)}"
            )
    
    async def _handle_tool_calls(self, response, func_tool, task_text, unified_msg_origin, reminder):
        """
        【重构】仅执行工具调用，不处理上下文，返回原始结果列表。
        """
        logger.info(f"检测到工具调用: {response.tools_call_name}")
        
        tool_results = []
        is_private_chat = self.message_handler.is_private_chat(unified_msg_origin)
        send_session_id = self._get_send_session_id(unified_msg_origin, is_private_chat)
        
        for i, func_name in enumerate(response.tools_call_name):
            func_args = response.tools_call_args[i] if i < len(response.tools_call_args) else {}
            tool_call_id = response.tools_call_id[i] if hasattr(response, 'tools_call_id') and response.tools_call_id else f"call_{i}"

            logger.info(f"执行工具调用: {func_name}({func_args})")
            
            func_result_str = ""
            try:
                func_obj = func_tool.get_func(func_name)
                if not func_obj:
                    raise ValueError(f"找不到函数处理器: {func_name}")

                event = self._create_event_object(task_text, unified_msg_origin, reminder, is_private_chat, send_session_id)
                
                if func_obj.handler:
                    func_result = await func_obj.handler(event, **func_args)
                elif func_obj.mcp_client:
                    if not func_obj.mcp_client.session:
                        raise RuntimeError(f"MCP客户端未初始化，无法调用函数 {func_name}")
                    func_result = await func_obj.mcp_client.session.call_tool(func_name, func_args)
                else:
                    func_result = await func_obj.execute(**func_args)
                
                logger.info(f"函数调用结果类型: {type(func_result)}, 值: {func_result}")
                
                if func_result is None:
                    func_result_str = "函数执行完成，无返回值。"
                elif hasattr(func_result, 'chain'):
                    func_result_str = func_result.get_plain_text() or "函数返回了复杂消息，但无文本内容。"
                else:
                    func_result_str = str(func_result)

            except Exception as e:
                logger.error(f"执行函数 {func_name} 时出错: {str(e)}")
                func_result_str = f"错误: {str(e)}"

            tool_results.append({
                "name": func_name,
                "result": func_result_str,
                "tool_call_id": tool_call_id
            })
            
        return tool_results

    async def _summarize_tool_results(self, tool_results, task_text, unified_msg_origin, provider, system_prompt: str) -> str:
        """
        【最终修复】不向模型传递 role:tool 历史，而是将工具结果包装在 prompt 中，并传入统一的人设。
        """
        if not tool_results:
            return "任务已执行。"

        # 构建一个简单的 prompt，其中包含工具的结果
        tool_results_text = ""
        for tr in tool_results:
            tool_results_text += f"- 工具 `{tr['name']}` 的执行结果:\n```\n{tr['result']}\n```\n"
        
        summary_prompt = f"""我执行了用户的任务"{task_text}"，并通过工具调用获得了以下结果：
        
{tool_results_text}

请对这些结果进行整理和润色，用自然、友好的语言向用户汇报任务的执行情况。直接回复用户，不要提及这是一个定时任务或你调用了什么工具。"""

        logger.info("二次调用LLM进行结果总结（安全模式，带人设）...")
        # 第二次调用，只使用 prompt，不传递复杂的 history，但传入统一的 system_prompt
        summary_response = await provider.text_chat(
            prompt=summary_prompt,
            session_id=unified_msg_origin,
            contexts=[], # 传递空上下文，避免兼容性问题
            func_tool=None, # 总结时不需要再调用工具
            system_prompt=system_prompt # 传入统一的人设
        )
        
        if summary_response and summary_response.completion_text:
            return summary_response.completion_text
        else:
            # 如果润色失败，返回一个格式化的原始结果
            result_text = "任务执行结果如下:\n"
            for tr in tool_results:
                result_text += f"[{tr['name']}]: {tr['result']}\n"
            return result_text.strip()

    async def _send_task_result(self, unified_msg_origin: str, reminder: dict, result_msg: MessageChain):
        """发送任务结果"""
        is_private_chat = self.message_handler.is_private_chat(unified_msg_origin)
        original_msg_origin = self._get_send_session_id(unified_msg_origin, is_private_chat)
        logger.info(f"尝试发送任务结果到: {original_msg_origin} (原始ID: {unified_msg_origin})")
        
        final_msg = MessageChain()
        
        should_at = self.config.get("enable_task_at", True)
        if reminder.get("is_command_task", False):
            should_at = self.config.get("enable_command_at", False)
        
        if should_at and not is_private_chat and "creator_id" in reminder and reminder["creator_id"]:
            self.message_handler._add_at_message(final_msg, original_msg_origin, reminder)
        
        for item in result_msg.chain:
            final_msg.chain.append(item)
        
        if not final_msg.chain or all(isinstance(c, At) and not getattr(c, 'name', True) for c in final_msg.chain):
             # 如果消息链为空，或只包含一个没有名字的@（可能发送失败），则不发送
            logger.warning("试图发送一条空消息或仅含无效@的消息，已中止。")
            return

        send_result = await self.context.send_message(original_msg_origin, final_msg)
        logger.info(f"任务结果消息发送结果: {send_result}")
    
    async def _update_conversation_history(self, original_msg_origin: str, curr_cid: str, new_contexts: list):
        """更新对话历史"""
        try:
            await self.context.conversation_manager.update_conversation(
                original_msg_origin, 
                curr_cid, 
                history=new_contexts
            )
            logger.info(f"任务流程已添加到对话历史，对话ID: {curr_cid}")
        except Exception as e:
            logger.error(f"更新任务对话历史失败: {str(e)}")


class ReminderExecutor:
    """处理提醒执行相关的功能"""
    
    def __init__(self, context, wechat_platforms, config=None):
        self.context = context
        self.wechat_platforms = wechat_platforms
        self.config = config or {}
        self.message_handler = ReminderMessageHandler(context, wechat_platforms, config)
    
    async def execute_reminder(self, unified_msg_origin: str, reminder: dict, provider):
        """执行提醒"""
        logger.info(f"Reminder Activated: {reminder['text']}, created by {unified_msg_origin}")
        
        enable_context = self.config.get("enable_context", True)
        max_context_count = self.config.get("max_context_count", 5)
        context_prompts = self.config.get("context_prompts", "")
        
        contexts = []
        curr_cid = None
        conversation = None
        
        if enable_context:
            try:
                original_msg_origin = self.message_handler.get_original_session_id(unified_msg_origin)
                curr_cid = await self.context.conversation_manager.get_curr_conversation_id(original_msg_origin)
                
                if curr_cid:
                    conversation = await self.context.conversation_manager.get_conversation(original_msg_origin, curr_cid)
                    if conversation:
                        history_json = conversation.history or "[]"
                        contexts = json.loads(history_json)
                        logger.info(f"提醒模式：找到用户对话，对话ID: {curr_cid}, 上下文长度: {len(contexts)}")
            except Exception as e:
                logger.warning(f"提醒模式：获取对话上下文失败: {str(e)}")
                contexts = []
        
        user_name = reminder.get("user_name", "用户")
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        
        if enable_context and len(contexts) > 2:
            prompt = f"""你现在需要向{user_name}发送一条预设的提醒。

当前时间是 {current_time}
提醒内容: {reminder['text']}

考虑到用户最近的对话内容，请以自然、友好的方式插入这条提醒。可以根据用户的聊天风格调整你的语气，但确保提醒内容清晰传达。
如果提醒内容与最近对话有关联，可以建立连接；如果无关，可以用适当的过渡语引入。

直接输出你要发送的提醒内容，无需说明这是提醒。"""
        else:
            if context_prompts:
                prompt = context_prompts.format(
                    user_name=user_name,
                    reminder_text=reminder['text'],
                    current_time=current_time
                )
            else:
                reminder_styles = [
                    f"嘿，{user_name}！这是你设置的提醒：{reminder['text']}",
                    f"提醒时间到了！{reminder['text']}",
                    f"别忘了：{reminder['text']}",
                    f"温馨提醒，{user_name}：{reminder['text']}",
                    f"时间提醒：{reminder['text']}",
                    f"叮咚！{reminder['text']}",
                ]
                chosen_style = random.choice(reminder_styles)
                prompt = f"""你需要提醒用户"{reminder['text']}"。
请以自然、友好的方式表达这个提醒，可以参考但不限于这种表达方式："{chosen_style}"。
根据提醒的内容，调整你的表达，使其听起来自然且贴心。直接输出你要发送的提醒内容，无需说明这是提醒。"""
        
        response = await provider.text_chat(
            prompt=prompt,
            session_id=unified_msg_origin,
            contexts=contexts[:max_context_count] if contexts and enable_context else []
        )
        
        await self.message_handler.send_reminder_message(unified_msg_origin, reminder, response.completion_text, is_task=False)
        
        if curr_cid and conversation and enable_context:
            try:
                new_contexts = contexts.copy()
                new_contexts.append({"role": "system", "content": f"系统在 {current_time} 触发了提醒: {reminder['text']}"})
                new_contexts.append({"role": "assistant", "content": response.completion_text})
                
                original_msg_origin = self.message_handler.get_original_session_id(unified_msg_origin)
                
                await self.context.conversation_manager.update_conversation(
                    original_msg_origin, 
                    curr_cid, 
                    history=new_contexts
                )
                logger.info(f"提醒已添加到对话历史，对话ID: {curr_cid}")
            except Exception as e:
                logger.error(f"更新提醒对话历史失败: {str(e)}")


class SimpleMessageSender:
    """处理简单消息发送"""
    
    def __init__(self, context, wechat_platforms, config=None):
        self.context = context
        self.wechat_platforms = wechat_platforms
        self.config = config or {}
        self.message_handler = ReminderMessageHandler(context, wechat_platforms, config)
    
    async def send_simple_message(self, unified_msg_origin: str, reminder: dict, is_task: bool = False, is_command_task: bool = False):
        """发送简单消息（当没有提供商时使用）"""
        logger.warning(f"没有可用的提供商，使用简单消息")
        
        msg = MessageChain()
        
        should_at = False
        if is_command_task:
            should_at = self.config.get("enable_command_at", False)
        elif is_task:
            should_at = self.config.get("enable_task_at", True)
        else:
            should_at = self.config.get("enable_reminder_at", True)
        
        if should_at and not self.message_handler.is_private_chat(unified_msg_origin) and "creator_id" in reminder and reminder["creator_id"]:
            original_msg_origin = self.message_handler.get_original_session_id(unified_msg_origin)
            self.message_handler._add_at_message(msg, original_msg_origin, reminder)
        
        prefix = "指令任务: " if is_command_task else "任务: " if is_task else "提醒: "
        msg.chain.append(Plain(f"{prefix}{reminder['text']}"))
        
        original_msg_origin = self.message_handler.get_original_session_id(unified_msg_origin)
        logger.info(f"尝试发送简单消息到: {original_msg_origin} (原始ID: {unified_msg_origin})")
        
        send_result = await self.context.send_message(original_msg_origin, msg)
        logger.info(f"消息发送结果: {send_result}")
        
        return send_result
