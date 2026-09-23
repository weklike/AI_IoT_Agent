"""Explicit model substitutes. Never selected on failure of the real provider."""

import asyncio
import copy
import json
import re
from uuid import uuid4

from backend.app.errors import DomainError


class ScriptedProvider:
    def __init__(self, responses: list[dict]):
        self.responses = responses
        self.requests: list[dict] = []
        self.delay = 0.0

    async def complete(self, messages, tools, timeout_s):
        self.requests.append(copy.deepcopy({"messages": messages, "tools": tools}))
        if self.delay:
            await asyncio.sleep(self.delay)
        if not self.responses:
            raise DomainError("FIXTURE_EXHAUSTED", "替身模型脚本已结束")
        return self.responses.pop(0)

    async def close(self):
        pass


def tool_response(name: str, args: dict) -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": str(uuid4()),
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)},
            }
        ],
    }


class FixtureProvider:
    """Deterministic demonstration script, with final values read only from actual tool outputs."""

    async def complete(self, messages, tools, timeout_s):
        question = next(message["content"] for message in messages if message["role"] == "user")
        match = re.search(r"CHG-(\d+)|(\d+)号", question, re.I)
        device_id = (
            f"CHG-{int(next(group for group in match.groups() if group)):03d}"
            if match
            else "CHG-002"
        )
        executed = [
            call["function"]["name"]
            for message in messages
            if message["role"] == "assistant"
            for call in message.get("tool_calls") or []
        ]
        results = [
            json.loads(message["content"]) for message in messages if message["role"] == "tool"
        ]
        if "知识检索" in question or "检索资料" in question:
            if not executed:
                return tool_response(
                    "search_fault_knowledge",
                    {"query": question[:300], "device_id": device_id if match else None},
                )
            result = results[0]
            matches = result["data"]["matches"]
            lines = ["【fixture 替身模型演示；不是实际模型推理】"]
            if not matches:
                lines.append("本次检索没有适用的知识依据，无法据此提供排查结论。")
            for source in matches:
                lines.append(
                    f"{source['title']}：{source['content']} [KB:{source['source_id']}@{source['version']}#{source['chunk_id']}]"
                )
            lines.append(f"[DATA:{result['tool_call_id']}]")
            return {"role": "assistant", "content": "\n\n".join(lines)}
        if "巡检" in question or "全站" in question:
            if not executed:
                minutes = re.search(r"(\d+)分钟", question)
                return tool_response(
                    "get_fleet_overview",
                    {"window_minutes": int(minutes.group(1)) if minutes else 30},
                )
            result = results[0]
            data = result["data"]
            lines = [
                "【fixture 替身模型演示；不是实际模型推理】",
                f"观测窗口：{data['from']} 至 {data['to']}。",
            ]
            for device in data["devices"]:
                state, stats = device["status"], device["statistics"]
                lines.append(
                    f"{device['device_id']}：{state['connection_state']}，新鲜={state['data_fresh']}；{stats['sample_count']}条样本。"
                )
                if stats["sample_count"]:
                    lines.append(
                        f"窗口温度均值{stats['temperature_avg_c']} °C，最高{stats['temperature_max_c']} °C；最后采样{state['sample_ts']}。"
                    )
                else:
                    lines.append("无样本，指标未知。")
            lines += [
                f"[DATA:{result['tool_call_id']}]",
                "可能原因：需要进一步查询证据。",
                "建议：先核对数据新鲜度与告警记录。",
            ]
            return {"role": "assistant", "content": "\n\n".join(lines)}
        if not executed:
            return tool_response("get_device_status", {"device_id": device_id})
        state = results[0].get("data") or {}
        reason = "OFFLINE" if state.get("connection_state") == "offline" else "OVERHEAT"
        analyze = any(word in question for word in ("分析", "排查", "原因", "为何", "过温"))
        history = analyze or any(
            word in question for word in ("历史", "最近", "分钟", "趋势", "平均", "最高")
        )
        if history and "get_device_history" not in executed:
            minutes = re.search(r"(\d+)分钟", question)
            window = int(minutes.group(1)) if minutes else 10
            return tool_response(
                "get_device_history", {"device_id": device_id, "window_minutes": window}
            )
        if analyze and "get_fault_guide" not in executed:
            return tool_response("get_fault_guide", {"reason_code": reason})
        authorized = any(tool["function"]["name"] == "create_work_order" for tool in tools)
        wants_order = any(word in question for word in ("建单", "创建", "建个", "建立", "建工单"))
        if authorized and wants_order and "create_work_order" not in executed:
            return tool_response(
                "create_work_order", {"device_id": device_id, "reason_code": reason}
            )
        lines = ["【fixture 替身模型演示；不是实际模型推理】"]
        for name, result in zip(executed, results):
            if not result["ok"]:
                lines.append(result["error"]["message"])
                continue
            data = result["data"]
            if name == "get_device_status":
                qualifier = "新鲜样本" if data["data_fresh"] else "数据已过期，仅为最后记录"
                lines.append(
                    f"{device_id}：{data['connection_state']} / {data['health_state']}。{qualifier}：{data['temperature_c']} °C，样本时间 {data['sample_ts']}。"
                )
            elif name == "get_device_history":
                lines.append(
                    f"窗口 {data['from']} 至 {data['to']}，{data['sample_count']} 条样本；平均 {data['temperature_avg_c']} °C，最高 {data['temperature_max_c']} °C，超限 {data['overheat_count']} 条。"
                )
            elif name == "get_fault_guide":
                lines.append(f"{data['source_id']} / {data['version']}：{data['content']}")
            elif name == "create_work_order":
                lines.append(
                    f"{'已创建' if data['created'] else '已复用'}工单 {data['order_id']}。"
                )
        if wants_order and not authorized:
            lines.append("本次未授权创建工单；如需建单，请启用本次工单授权后重新提交。")
        return {"role": "assistant", "content": "\n\n".join(lines)}

    async def close(self):
        pass
