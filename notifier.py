# -*- coding: utf-8 -*-
import os
import requests
import resend
import pandas as pd
from datetime import datetime, timedelta

def build_taiwan_summary(report_df, stats=None, max_candidates=5):
    """Summarize validated 5-trading-day returns; never mislabel them as daily breadth."""
    stats = stats or {}
    if report_df is None or report_df.empty:
        return "⚠️ 分析樣本為空，沒有可用的市場摘要。"
    lines = ["📊 <b>台股收盤研究摘要</b>", f"分析樣本：{len(report_df)} 檔"]
    if stats.get("current_date") is not None and stats.get("total") is not None:
        lines.append(f"符合共同最新行情日：{stats.get('current_date')}/{stats.get('total')} 檔")
    if "Day_Close" in report_df.columns:
        daily = pd.to_numeric(report_df["Day_Close"], errors="coerce").dropna()
        if not daily.empty:
            up, down, flat = int((daily > 0).sum()), int((daily < 0).sum()), int((daily == 0).sum())
            lines.extend(["", "<b>單日市場廣度（共同最新交易日）</b>",
                          f"上漲 {up}／下跌 {down}／持平 {flat}（樣本 {len(daily)} 檔）",
                          f"平均 {daily.mean():.2f}%｜中位數 {daily.median():.2f}%"])
    if "Week_Close" in report_df.columns:
        values = pd.to_numeric(report_df["Week_Close"], errors="coerce").dropna()
        if not values.empty:
            up, down, flat = int((values > 0).sum()), int((values < 0).sum()), int((values == 0).sum())
            lines.extend(["", "<b>近 5 交易日報酬概況（非單日漲跌家數）</b>",
                          f"上漲 {up}／下跌 {down}／持平 {flat}",
                          f"平均報酬 {values.mean():.2f}%｜中位數 {values.median():.2f}%"])
    if {"Week_Close", "Ticker"}.issubset(report_df.columns):
        ranked = report_df[["Ticker", "Week_Close"]].copy()
        ranked["Week_Close"] = pd.to_numeric(ranked["Week_Close"], errors="coerce")
        ranked = ranked.dropna().nlargest(max_candidates, "Week_Close")
        if not ranked.empty:
            lines.extend(["", "<b>近 5 交易日報酬領先觀察（研究排序）</b>"])
            for row in ranked.itertuples(index=False):
                lines.append(f"• {row.Ticker}：{row.Week_Close:.2f}%")
    lines.extend(["", "⚠️ 5 日報酬不代表今日漲跌，亦非買賣訊號。"])
    return "\n".join(lines)



def notification_config_status(env=None):
    """Report credential presence only; never expose secret values."""
    env = os.environ if env is None else env
    return {
        'email_api_key_present': bool(env.get('RESEND_API_KEY')),
        'email_recipient_present': bool(env.get('REPORT_RECEIVER_EMAIL')),
        'telegram_token_present': bool(env.get('TELEGRAM_BOT_TOKEN')),
        'telegram_chat_id_present': bool(env.get('TELEGRAM_CHAT_ID')),
    }

def deliver_notification_channels(email_configured, telegram_configured,
                                  send_email, send_telegram, logger=print):
    """Attempt configured channels independently; succeed if at least one delivers."""
    email_sent = False
    telegram_sent = False
    if email_configured:
        try:
            send_email()
            email_sent = True
            logger("NOTIFY_EMAIL_SUCCESS")
        except Exception as exc:
            logger(f"NOTIFY_EMAIL_FAILED error={type(exc).__name__}: {exc}")
    else:
        logger("NOTIFY_EMAIL_SKIPPED")

    if telegram_configured:
        try:
            telegram_sent = bool(send_telegram(email_sent))
            logger("NOTIFY_TELEGRAM_SUCCESS" if telegram_sent else "NOTIFY_TELEGRAM_FAILED")
        except Exception as exc:
            logger(f"NOTIFY_TELEGRAM_FAILED error={type(exc).__name__}: {exc}")
    else:
        logger("NOTIFY_TELEGRAM_SKIPPED")

    if not email_configured and not telegram_configured:
        logger("NOTIFY_NO_CHANNEL_CONFIGURED")
        return False, email_sent, telegram_sent
    if not email_sent and not telegram_sent:
        logger("NOTIFY_ALL_CONFIGURED_CHANNELS_FAILED")
        return False, email_sent, telegram_sent
    return True, email_sent, telegram_sent


class StockNotifier:
    def __init__(self):
        # 從環境變數讀取金鑰與 ID
        self.tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.tg_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.resend_api_key = os.getenv("RESEND_API_KEY")
        self.report_receiver_email = os.getenv("REPORT_RECEIVER_EMAIL")
        
        if self.resend_api_key:
            resend.api_key = self.resend_api_key

    def get_now_time_str(self):
        """獲取 UTC+8 台北時間"""
        now_utc8 = datetime.utcnow() + timedelta(hours=8)
        return now_utc8.strftime("%Y-%m-%d %H:%M:%S")

    def send_telegram(self, message):
        """發送 Telegram 即時簡報"""
        if not self.tg_token or not self.tg_chat_id:
            return False
        
        # 取得簡短時間戳
        ts = self.get_now_time_str().split(" ")[1]
        full_message = f"{message}\n\n🕒 <i>Sent at {ts} (UTC+8)</i>"
        
        url = f"https://api.telegram.org/bot{self.tg_token}/sendMessage"
        payload = {
            "chat_id": self.tg_chat_id, 
            "text": full_message, 
            "parse_mode": "HTML"
        }
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            result = response.json()
            if not result.get("ok", False):
                raise RuntimeError(f"Telegram API rejected message: {result}")
            return True
        except Exception as e:
            print(f"⚠️ Telegram 發送失敗: {e}")
            return False

    def send_stock_report(self, market_name, img_data, report_df, text_reports, stats=None):
        """
        🚀 專業版更新：整合智慧下載統計、六國專業平台跳轉
        支援：將下載器 (Downloader) 的統計結果完美呈現於 HTML 報表頂端
        """
        # 🟢 Debug 訊息：方便在終端機確認 main.py 傳進來的數值
        print(f"DEBUG: notifier 正在處理 {market_name} 報告 (Stats: {stats})")

        tg_summary = build_taiwan_summary(report_df, stats) if "台灣" in market_name else (
            f"📊 <b>{market_name} 監控分析已完成</b>\n有效分析樣本：{len(report_df)} 檔"
        )
        report_time = self.get_now_time_str()
        
        # --- 1. 處理下載統計數據 (防止 0 或 None 導致報表崩潰) ---
        if stats is None:
            stats = {}

        # 應收標的：優先從 stats 拿，拿不到就看 report_df
        total_count = stats.get('total', len(report_df))
        # 可用資料數（包含快取）；另行計算符合共同最新交易日的筆數
        success_count = stats.get('success', len(report_df))
        current_date_count = stats.get('current_date', success_count)
        stale_date_count = stats.get('stale_date', max(0, int(success_count) - int(current_date_count)))

        try:
            total_val = int(total_count)
            success_val = int(success_count)
            current_val = int(current_date_count)
            if total_val > 0:
                success_rate = f"{(success_val / total_val) * 100:.1f}%"
                current_date_rate = f"{(current_val / total_val) * 100:.1f}%"
            else:
                success_rate = "0.0%"
                current_date_rate = "0.0%"
        except (TypeError, ValueError):
            success_rate = "N/A"
            current_date_rate = "N/A"

        # --- 💡 智慧匹配平台跳轉連結 ---
        m_id = market_name.lower()
        if "us" in m_id or "美國" in market_name:
            p_name, p_url = "StockCharts", "https://stockcharts.com/"
        elif "hk" in m_id or "香港" in market_name:
            p_name, p_url = "AASTOCKS 阿思達克", "http://www.aastocks.com/"
        elif "cn" in m_id or "中國" in market_name:
            p_name, p_url = "東方財富網 (EastMoney)", "https://www.eastmoney.com/"
        elif "jp" in m_id or "日本" in market_name:
            p_name, p_url = "樂天證券 (Rakuten)", "https://www.rakuten-sec.co.jp/"
        elif "kr" in m_id or "韓國" in market_name:
            p_name, p_url = "Naver Finance", "https://finance.naver.com/"
        else:
            p_name, p_url = "玩股網 (WantGoo)", "https://www.wantgoo.com/"

        # --- 2. 構建 HTML 內容 ---
        html_content = f"""
        <html>
        <body style="font-family: 'Microsoft JhengHei', sans-serif; color: #333; line-height: 1.6;">
            <div style="max-width: 800px; margin: auto; border: 1px solid #ddd; border-top: 10px solid #28a745; border-radius: 10px; padding: 25px;">
                <h2 style="color: #1a73e8; border-bottom: 2px solid #eee; padding-bottom: 10px;">{market_name} 全方位監控報告</h2>
                <p style="color: #666;">生成時間: <b>{report_time} (台北時間)</b></p>
                
                <div style="background-color: #f8f9fa; padding: 15px; border-radius: 8px; margin: 20px 0; display: flex; justify-content: space-around; border: 1px solid #eee; text-align: center;">
                    <div style="flex: 1;">
                        <div style="font-size: 12px; color: #888;">應收標的</div>
                        <div style="font-size: 18px; font-weight: bold;">{total_count}</div>
                    </div>
                    <div style="flex: 1; border-left: 1px solid #eee; border-right: 1px solid #eee;">
                        <div style="font-size: 12px; color: #888;">資料可用(含快取)</div>
                        <div style="font-size: 18px; font-weight: bold; color: #28a745;">{success_count}</div>
                    </div>
                    <div style="flex: 1;">
                        <div style="font-size: 12px; color: #888;">符合最新行情日</div>
                        <div style="font-size: 18px; font-weight: bold; color: #1a73e8;">{current_date_count}/{total_count} ({current_date_rate})</div>
                    </div>
                </div>

                <p style="background-color: #fff9db; padding: 12px; border-left: 4px solid #fcc419; font-size: 14px; color: #666; margin: 20px 0;">
                    💡 <b>提示：</b>下方的數據報表若包含股票代號，可至  
                    <a href="{p_url}" target="_blank" style="color: #e67e22; text-decoration: none; font-weight: bold;">{p_name}</a> 
                    查看該市場之即時技術線圖。
                </p>
        """

        # --- 3. 插入收盤研究摘要 ---
        if "台灣" in market_name:
            summary_text = build_taiwan_summary(report_df, stats)
            summary_html = "<br>".join(
                line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                for line in summary_text.splitlines()
            )
            html_content += (
                "<div style='margin:24px 0;padding:16px;border:1px solid #d9e2f0;"
                "border-radius:8px;background:#f7faff;'>"
                "<h3 style='margin-top:0;'>收盤研究摘要</h3>"
                f"<div>{summary_html}</div></div>"
            )

        # --- 4. 插入九張分析矩陣圖表 ---
        html_content += "<div style='margin-top: 30px;'>"
        for img in img_data:
            html_content += f"""
            <div style="margin-bottom: 40px; text-align: center; border-bottom: 1px dashed #eee; padding-bottom: 25px;">
                <h3 style="color: #2c3e50; text-align: left; font-size: 16px; border-left: 4px solid #3498db; padding-left: 10px;">📍 {img['label']}</h3>
                <img src="cid:{img['id']}" style="width: 100%; max-width: 750px; border-radius: 5px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); margin-top: 10px;">
            </div>
            """
        html_content += "</div>"

        # --- 4. 插入文字報酬分布明細 ---
        html_content += "<div style='margin-top: 20px;'>"
        for period, report in text_reports.items():
            p_name_zh = {"Week": "週", "Month": "月", "Year": "年"}.get(period, period)
            html_content += f"""
            <div style="margin-bottom: 20px;">
                <h4 style="color: #16a085; margin-bottom: 8px;">📊 {p_name_zh} K線 最高-進攻 報酬分布明細</h4>
                <pre style="background-color: #2d3436; color: #dfe6e9; padding: 15px; border-radius: 5px; font-size: 12px; white-space: pre-wrap; font-family: 'Courier New', monospace;">{report}</pre>
            </div>
            """
        html_content += "</div>"

        html_content += """
                <p style="margin-top: 40px; font-size: 11px; color: #999; text-align: center; border-top: 1px solid #eee; padding-top: 20px;">
                    此郵件由 Global Stock Monitor 系統自動發送。數據僅供參考，不構成投資建議。
                </p>
            </div>
        </body>
        </html>
        """

        # --- 5. 處理附件 (Inline Embedding) ---
        attachments = []
        for img in img_data:
            try:
                if os.path.exists(img['path']):
                    with open(img['path'], "rb") as f:
                        attachments.append({
                            "content": list(f.read()),
                            "filename": f"{img['id']}.png",
                            "content_id": img['id'],
                            "disposition": "inline"
                        })
                else:
                    print(f"⚠️ 圖表檔案不存在: {img['path']}")
            except Exception as e:
                print(f"⚠️ 處理圖表附件失敗 {img['id']}: {e}")

        # --- 6. Email 與 Telegram 分離發送；單一通道失敗不得阻斷另一通道 ---
        email_configured = bool(self.resend_api_key and self.report_receiver_email)
        telegram_configured = bool(self.tg_token and self.tg_chat_id)
        config_status = notification_config_status()
        print("NOTIFY_CONFIG " + " ".join(f"{key}={value}" for key, value in config_status.items()))
        email_payload = {
            "from": "StockMonitor <onboarding@resend.dev>",
            "to": self.report_receiver_email,
            "subject": f"🚀 {market_name} 全方位監控報告 - {report_time.split(' ')[0]}",
            "html": html_content,
            "attachments": attachments
        }
        success, email_sent, telegram_sent = deliver_notification_channels(
            email_configured=email_configured,
            telegram_configured=telegram_configured,
            send_email=lambda: resend.Emails.send(email_payload),
            send_telegram=lambda email_sent: self.send_telegram(
                tg_summary + f"\n\nEmail 報告：{'已寄送' if email_sent else '未設定或寄送失敗'}"
                f"\n資料可用率：{success_rate}"
            ),
            logger=lambda message: print(f"{message} market={market_name}")
        )
        print(f"NOTIFY_RESULT email={email_sent} telegram={telegram_sent}")
        return success