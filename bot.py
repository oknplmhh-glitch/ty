import os
from flask import Flask
from threading import Thread
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

BOT_TOKEN = os.getenv("BOT_TOKEN")

web_app = Flask(__name__)

@web_app.route("/")
def home():
    return "Bot is running"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)

Thread(target=run_web, daemon=True).start()

group_data = {}


def get_gdata(cid):
    if cid not in group_data:
        group_data[cid] = {
            "rate_ex": 0,
            "rate_fee": 0,
            "total_in": 0,
            "total_out": 0,
            "hidden_u": 0,
            "list_in": [],
            "list_out": []
        }
    return group_data[cid]


async def send_bill(chat_id, ctx, data):
    fee_percent = 100 - data["rate_fee"]

    in_lines = []
    for i in data["list_in"]:
        if data["rate_ex"] > 0:
            u = round((i["num"] / data["rate_ex"]) * (fee_percent / 100), 3)
            line = f'{i["time"]}  {i["num"]}/{data["rate_ex"]}*{fee_percent}% ={u}u {i["name"]}'
        else:
            line = f'{i["time"]}  {i["num"]} {i["name"]}'
        in_lines.append(line)

    out_lines = []
    for o in data["list_out"]:
        if data["rate_ex"] > 0:
            u = round((o["num"] / data["rate_ex"]) * (fee_percent / 100), 3)
            line = f'{o["time"]}  {o["num"]}/{data["rate_ex"]}*{fee_percent}% ={u}u'
        else:
            line = f'{o["time"]}  {o["num"]}'
        out_lines.append(line)

    in_text = "\n".join(in_lines)
    out_text = "\n".join(out_lines)

    if data["rate_ex"] <= 0:
        in_rmb_real = 0
        out_rmb_real = 0
        in_usd = 0
        out_usd = data["hidden_u"]
        remain_usd = 0
    else:
        in_rmb_real = round(data["total_in"] * (fee_percent / 100), 3)
        out_rmb_real = round(data["total_out"] * (fee_percent / 100), 3)

        in_usd = round(in_rmb_real / data["rate_ex"], 3)
        normal_out_usd = round(out_rmb_real / data["rate_ex"], 3)

        out_usd = round(normal_out_usd + data["hidden_u"], 3)
        remain_usd = round(in_usd - out_usd, 3)

    out_total_show = round(data["total_out"] + data["hidden_u"], 3)

    msg = f"""
总入（{len(data["list_in"])}）
{in_text}

总出（{len(data["list_out"])}）
{out_text}

入账汇率：{data["rate_ex"]}
入账费率：{data["rate_fee"]}%
入账总数：{data["total_in"]}
入账合计：{in_rmb_real} | {in_usd}U

下发总数：{out_total_show}
下发合计：{out_rmb_real} | {out_usd}U

合计未回：{remain_usd} USD
"""

    await ctx.bot.send_message(chat_id, msg.strip())


async def main_handle(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message

    if not msg or not msg.text:
        return

    chat_id = msg.chat.id
    text = msg.text.strip()
    d = get_gdata(chat_id)

    if text.startswith("设置汇率"):
        try:
            num = float(text.replace("设置汇率", "").strip())
            d["rate_ex"] = num
            await msg.reply_text(f"✅ 汇率设置成功，当前汇率：{num}")
        except:
            await msg.reply_text("❌ 格式错误，例如：设置汇率6.76")

    elif text.startswith("设置费率"):
        try:
            num = float(text.replace("设置费率", "").strip())
            d["rate_fee"] = num
            await msg.reply_text(f"✅ 费率设置成功，入账费率：{num}%")
        except:
            await msg.reply_text("❌ 格式错误，例如：设置费率9")

    elif text.startswith("+"):
        try:
            money = float(text[1:].strip())

            if money == 0:
                await send_bill(chat_id, ctx, d)
                return

            nick = ""
            if msg.reply_to_message:
                nick = msg.reply_to_message.from_user.full_name

            now_time = datetime.now().strftime("%m-%d %H:%M")

            d["list_in"].append({
                "time": now_time,
                "num": money,
                "name": nick
            })

            d["total_in"] += money
            await send_bill(chat_id, ctx, d)

        except:
            pass

    elif text.startswith("下发"):
        try:
            raw = text.replace("下发", "").strip()

            if raw.lower().endswith("u"):
                money = float(raw[:-1])
                d["hidden_u"] += money
            else:
                money = float(raw)

                now_time = datetime.now().strftime("%m-%d %H:%M")

                d["list_out"].append({
                    "time": now_time,
                    "num": money
                })

                d["total_out"] += money

            await send_bill(chat_id, ctx, d)

        except:
            pass

    elif text == "撤销入款":
        if d["list_in"]:
            last = d["list_in"].pop()
            d["total_in"] -= last["num"]

        await send_bill(chat_id, ctx, d)

    elif text == "撤销出款":
        if d["list_out"]:
            last = d["list_out"].pop()
            d["total_out"] -= last["num"]

        await send_bill(chat_id, ctx, d)

    elif text == "清除今日数据":
        d["total_in"] = 0
        d["total_out"] = 0
        d["hidden_u"] = 0

        d["list_in"].clear()
        d["list_out"].clear()

        await msg.reply_text("✅ 今日所有数据已清空")
        await send_bill(chat_id, ctx, d)


if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            main_handle
        )
    )

    print("机器人已启动")
    app.run_polling()
