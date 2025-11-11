"""
Streamlit Web界面
为Deep Search Agent提供友好的Web界面
"""

import os
import sys
import streamlit as st
from datetime import datetime
import json
from fpdf import FPDF
try:
    import markdown as md  # 用于将Markdown转为HTML
except Exception:
    md = None
from fpdf.html import HTMLMixin
import urllib.request

# 添加src目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src import DeepSearchAgent, Config


# 历史记录数据库路径（指向项目根目录）
HISTORY_DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "history.db"))

# PDF中文字体配置
FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
FONT_PATH = os.path.join(FONT_DIR, "NotoSansCJKsc-Regular.otf")
FONT_DOWNLOAD_URL = "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf"


def ensure_chinese_font():
    """确保存在支持中文的字体文件"""
    if os.path.exists(FONT_PATH):
        return True, None
    try:
        os.makedirs(FONT_DIR, exist_ok=True)
        urllib.request.urlretrieve(FONT_DOWNLOAD_URL, FONT_PATH)
        return True, None
    except Exception as e:
        return False, str(e)


class PDF(FPDF, HTMLMixin):
    pass


def generate_pdf_report(content: str):
    """使用FPDF生成支持中文的PDF报告"""
    font_ready, font_error = ensure_chinese_font()
    if not font_ready:
        return None, f"下载中文字体失败: {font_error}"
    try:
        pdf = PDF(orientation="P", unit="mm", format="A4")
        # 统一设置页边距，确保有效宽度充足
        pdf.set_margins(left=12, top=15, right=12)
        pdf.add_font("NotoSansSC", "", FONT_PATH, uni=True)
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        # 动态选择安全字体大小，避免单字符也无法放下的情况
        def choose_font_size() -> int:
            size = 12
            effective_width = pdf.w - pdf.l_margin - pdf.r_margin
            # 选择代表性的中英文字符进行宽度测试
            test_chars = ["汉", "W"]
            while size >= 7:
                pdf.set_font("NotoSansSC", size=size)
                if max(pdf.get_string_width(ch) for ch in test_chars) < effective_width:
                    return size
                size -= 1
            return 7
        base_size = choose_font_size()
        pdf.set_font("NotoSansSC", size=base_size)
        line_height = base_size * 0.6  # 合理的行高
        effective_width = pdf.w - pdf.l_margin - pdf.r_margin
        # 优先：将Markdown转换为HTML并用HTML渲染，以保留基础样式
        rendered = False
        if md is not None:
            try:
                html = md.markdown(
                    content,
                    extensions=["extra", "sane_lists", "nl2br"]
                )
                # 设置当前字体后渲染HTML
                pdf.set_font("NotoSansSC", size=base_size)
                pdf.write_html(html)
                rendered = True
            except Exception:
                rendered = False
        # 回退：逐行写入纯文本
        if not rendered:
            for raw_line in content.split("\n"):
                line = raw_line if raw_line is not None else ""
                if line.strip() == "":
                    pdf.ln(line_height)
                    continue
                pdf.set_x(pdf.l_margin)
                try:
                    pdf.multi_cell(effective_width, line_height, line)
                except Exception:
                    # 退路1：插入零宽空格以帮助换行
                    try:
                        safe_line = "\u200b".join(list(line))
                        pdf.multi_cell(effective_width, line_height, safe_line)
                    except Exception:
                        # 退路2：降级为可编码字符
                        ascii_fallback = line.encode("latin-1", "replace").decode("latin-1")
                        pdf.multi_cell(effective_width, line_height, ascii_fallback)
        output_buffer = pdf.output(dest="S")
        if isinstance(output_buffer, (bytes, bytearray)):
            pdf_bytes = bytes(output_buffer)
        else:
            # 兼容旧版本返回 str 的情况
            pdf_bytes = str(output_buffer).encode("latin1", errors="replace")
        return pdf_bytes, None
    except Exception as e:
        return None, str(e)


def get_history_records():
    """获取所有历史记录"""
    import sqlite3
    try:
        conn = sqlite3.connect(HISTORY_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS research_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                report TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            SELECT id, query, report, created_at 
            FROM research_history 
            ORDER BY created_at DESC
        """)
        records = cursor.fetchall()
        conn.close()
        return records
    except Exception as e:
        st.error(f"读取历史记录失败: {str(e)}")
        return []


def get_history_record_by_id(record_id: int):
    """根据ID获取历史记录"""
    import sqlite3
    try:
        conn = sqlite3.connect(HISTORY_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, query, report, created_at 
            FROM research_history 
            WHERE id = ?
        """, (record_id,))
        record = cursor.fetchone()
        conn.close()
        return record
    except Exception as e:
        st.error(f"读取历史记录失败: {str(e)}")
        return None


def delete_history_record(record_id: int):
    """删除历史记录"""
    import sqlite3
    try:
        conn = sqlite3.connect(HISTORY_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM research_history WHERE id = ?", (record_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"删除历史记录失败: {str(e)}")
        return False


def format_datetime(created_at):
    """格式化时间"""
    if isinstance(created_at, str):
        return created_at
    elif hasattr(created_at, 'strftime'):
        return created_at.strftime("%Y-%m-%d %H:%M:%S")
    else:
        return str(created_at)


def main():
    """主函数"""
    st.set_page_config(
        page_title="WGD Deep Search",
        page_icon="🔍",
        layout="wide"
    )
    
    st.title("WGD Deep Search")
    st.markdown("基于DeepSeek的无框架深度搜索AI代理")
    
    # API密钥配置（可编辑并保存到SQLite数据库）
    import sqlite3

    DB_PATH = os.path.join(os.path.dirname(__file__), "apikeys.db")

    # 初始化数据库
    def init_db():
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                name TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.commit()
        conn.close()
    
    def load_api_key(name):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM api_keys WHERE name=?", (name,))
        result = cursor.fetchone()
        conn.close()
        if result:
            return result[0]
        return ""
    
    def save_api_key(name, value):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("REPLACE INTO api_keys (name, value) VALUES (?, ?)", (name, value))
        conn.commit()
        conn.close()

    # 初始化DB（只需运行一次）
    init_db()
    
    # 主标签页：新研究和历史记录
    main_tab1, main_tab2 = st.tabs(["🔍 新研究", "📚 历史记录"])
    
    # 侧边栏配置
    with st.sidebar:
        st.header("配置")

        st.subheader("API密钥")

        # 读取已保存的key
        deepseek_default = load_api_key("deepseek")
        tavily_default = load_api_key("tavily")
        
        # 初始化API密钥变量（从数据库或查询参数）
        # 优先使用查询参数，否则使用数据库中的值
        deepseek_key = deepseek_default
        tavily_key = tavily_default
        
        # 从查询参数获取（如果存在）
        if "deepseek_key" in st.query_params:
            param_value = st.query_params.get("deepseek_key")
            deepseek_key = param_value[0] if isinstance(param_value, list) and len(param_value) > 0 else param_value
        if "tavily_key" in st.query_params:
            param_value = st.query_params.get("tavily_key")
            tavily_key = param_value[0] if isinstance(param_value, list) and len(param_value) > 0 else param_value

        # 表单更新
        # 为了防止浏览器密码保存/生成，使用自定义HTML输入框并关闭自动填充
        import streamlit.components.v1 as components

        with st.form("apikey_form"):

            deepseek_html = f"""
            <input 
                type="password" 
                name="deepseek_key" 
                id="deepseek_key" 
                value="{deepseek_default}" 
                autocomplete="off" 
                autocorrect="off" 
                autocapitalize="off" 
                spellcheck="false" 
                placeholder="DeepSeek API Key"
                style="width: 100%; padding: 0.5em; border-radius: 0.3em; border: 1px solid #ccc;"
                onfocus="this.removeAttribute('autocomplete');"
            >
            """
            tavily_html = f"""
            <input 
                type="password" 
                name="tavily_key" 
                id="tavily_key" 
                value="{tavily_default}" 
                autocomplete="off" 
                autocorrect="off" 
                autocapitalize="off" 
                spellcheck="false" 
                placeholder="Tavily API Key"
                style="width: 100%; padding: 0.5em; border-radius: 0.3em; border: 1px solid #ccc;"
                onfocus="this.removeAttribute('autocomplete');"
            >
            """
            st.markdown("DeepSeek API Key")
            components.html(deepseek_html, height=40)
            st.markdown("Tavily API Key")
            components.html(tavily_html, height=40)

            submitted = st.form_submit_button("保存API密钥")
            # 通过QueryString hack（或利用streamlit_js_eval的js回传）无法直接取components的值，这里采取streamlit原生的text_input临时方案
            # 但会告知用户避免保存密码
            if submitted:
                # 回落到streamlit的text_input，以便可以真正获取用户输入
                # 但通过添加autocomplete="off"建议浏览器不保存密码
                new_deepseek_key = st.text_input("DeepSeek API Key（请勿保存密码）", type="password", value=deepseek_default, key="deepseek_form_key", autocomplete="off", label_visibility="collapsed")
                new_tavily_key = st.text_input("Tavily API Key（请勿保存密码）", type="password", value=tavily_default, key="tavily_form_key", autocomplete="off", label_visibility="collapsed")
                save_api_key("deepseek", new_deepseek_key)
                save_api_key("tavily", new_tavily_key)
                # 更新当前会话的值
                deepseek_key = new_deepseek_key
                tavily_key = new_tavily_key
                st.success("API密钥已保存")
                # 重新加载数据库中的值（用于下次运行）
                deepseek_default = load_api_key("deepseek")
                tavily_default = load_api_key("tavily")
        
        # 高级配置
        st.subheader("高级配置")
        max_reflections = st.slider("反思次数", 1, 5, 2)
        max_search_results = st.slider("搜索结果数", 1, 10, 3)
        max_content_length = st.number_input("最大内容长度", 1000, 50000, 20000)
        
        # 模型选择
        llm_provider = st.selectbox("LLM提供商", ["deepseek", "openai"])
        
        if llm_provider == "deepseek":
            model_name = st.selectbox("DeepSeek模型", ["deepseek-chat"])
        else:
            model_name = st.selectbox("OpenAI模型", ["gpt-4o-mini", "gpt-4o"])
            openai_key = st.text_input("OpenAI API Key", type="password",
                                     value="")
    
    # 新研究标签页
    with main_tab1:
        # 主界面
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.header("研究查询")
            query = st.text_area(
                "请输入您要研究的问题",
                placeholder="例如：2025年人工智能发展趋势",
                height=100
            )
            
            # 预设查询示例
            st.subheader("示例查询")
            example_queries = [
                "2025年人工智能发展趋势",
                "深度学习在医疗领域的应用",
                "区块链技术的最新发展",
                "可持续能源技术趋势",
                "量子计算的发展现状"
            ]
            
            selected_example = st.selectbox("选择示例查询", ["自定义"] + example_queries)
            if selected_example != "自定义":
                query = selected_example
        
        with col2:
            st.header("状态信息")
            if 'agent' in st.session_state and hasattr(st.session_state.agent, 'state'):
                progress = st.session_state.agent.get_progress_summary()
                st.metric("总段落数", progress['total_paragraphs'])
                st.metric("已完成", progress['completed_paragraphs'])
                st.progress(progress['progress_percentage'] / 100)
            else:
                st.info("尚未开始研究")
        
        # 执行按钮
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            start_research = st.button("开始研究", type="primary", use_container_width=True)
        
        # 验证配置
        if start_research:
            # 重新从数据库加载API密钥，确保使用最新值
            deepseek_key = load_api_key("deepseek")
            tavily_key = load_api_key("tavily")
            
            if not query.strip():
                st.error("请输入研究查询")
                return
            
            if not deepseek_key and llm_provider == "deepseek":
                st.error("请提供DeepSeek API Key")
                return
            
            if not tavily_key:
                st.error("请提供Tavily API Key")
                return
            
            if llm_provider == "openai" and not openai_key:
                st.error("请提供OpenAI API Key")
                return
            
            # 创建配置
            config = Config(
                deepseek_api_key=deepseek_key if llm_provider == "deepseek" else None,
                openai_api_key=openai_key if llm_provider == "openai" else None,
                tavily_api_key=tavily_key,
                default_llm_provider=llm_provider,
                deepseek_model=model_name if llm_provider == "deepseek" else "deepseek-chat",
                openai_model=model_name if llm_provider == "openai" else "gpt-4o-mini",
                max_reflections=max_reflections,
                max_search_results=max_search_results,
                max_content_length=max_content_length,
                output_dir="streamlit_reports"
            )
            
            # 执行研究
            execute_research(query, config)
    
    # 历史记录标签页
    with main_tab2:
        st.header("历史记录")
        
        # 获取所有历史记录
        records = get_history_records()
        
        if not records:
            st.info("暂无历史记录")
        else:
            # 创建记录选择器
            record_options = {}
            for record in records:
                record_id, query, report, created_at = record
                # 格式化时间
                time_str = format_datetime(created_at)
                # 显示格式：ID - 查询内容 - 时间
                display_text = f"#{record_id} - {query[:50]}{'...' if len(query) > 50 else ''} - {time_str}"
                record_options[display_text] = record_id
            
            selected_record_key = st.selectbox(
                "选择历史记录",
                options=["请选择..."] + list(record_options.keys()),
                key="history_selector"
            )
            
            if selected_record_key != "请选择...":
                selected_record_id = record_options[selected_record_key]
                record = get_history_record_by_id(selected_record_id)
                
                if record:
                    record_id, query, report, created_at = record
                    
                    # 显示记录信息
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.subheader(f"查询: {query}")
                    with col2:
                        time_str = format_datetime(created_at)
                        st.caption(f"创建时间: {time_str}")
                        if st.button("删除记录", key=f"delete_{record_id}", type="secondary"):
                            if delete_history_record(record_id):
                                st.success("记录已删除")
                                st.rerun()
                    
                    # 显示报告内容
                    st.divider()
                    st.subheader("报告内容")
                    st.markdown(report)
                    
                    # 下载选项
                    st.divider()
                    st.subheader("下载报告")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.download_button(
                            label="下载Markdown报告",
                            data=report,
                            file_name=f"deep_search_report_{record_id}_{time_str.replace(' ', '_').replace(':', '-')}.md",
                            mime="text/markdown",
                            key=f"download_md_{record_id}"
                        )
                    with col2:
                        # PDF下载（历史记录）
                        pdf_bytes, pdf_err = generate_pdf_report(report)
                        st.download_button(
                            label="下载PDF报告",
                            data=pdf_bytes if pdf_bytes else b"",
                            file_name=f"deep_search_report_{record_id}_{time_str.replace(' ', '_').replace(':', '-')}.pdf",
                            mime="application/pdf",
                            disabled=pdf_bytes is None,
                            key=f"download_pdf_{record_id}"
                        )
                        if pdf_err:
                            st.caption(f"PDF生成失败：{pdf_err}")


def execute_research(query: str, config: Config):
    """执行研究"""
    try:
        import sqlite3
        
        # 创建进度条
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # 初始化Agent
        status_text.text("正在初始化Agent...")
        agent = DeepSearchAgent(config)
        st.session_state.agent = agent
        
        progress_bar.progress(10)
        
        # 生成报告结构
        status_text.text("正在生成报告结构...")
        agent._generate_report_structure(query)
        progress_bar.progress(20)
        
        # 处理段落
        total_paragraphs = len(agent.state.paragraphs)
        for i in range(total_paragraphs):
            status_text.text(f"正在处理段落 {i+1}/{total_paragraphs}: {agent.state.paragraphs[i].title}")
            
            # 初始搜索和总结
            agent._initial_search_and_summary(i)
            progress_value = 20 + (i + 0.5) / total_paragraphs * 60
            progress_bar.progress(int(progress_value))
            
            # 反思循环
            agent._reflection_loop(i)
            agent.state.paragraphs[i].research.mark_completed()
            
            progress_value = 20 + (i + 1) / total_paragraphs * 60
            progress_bar.progress(int(progress_value))
        
        # 生成最终报告
        status_text.text("正在生成最终报告...")
        final_report = agent._generate_final_report()
        progress_bar.progress(90)
        
        # 保存报告
        status_text.text("正在保存报告...")
        agent._save_report(final_report)
        progress_bar.progress(100)
        
        status_text.text("研究完成！")
        
        # --- 数据库存储 ---
        try:
            conn = sqlite3.connect(HISTORY_DB_PATH)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS research_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT NOT NULL,
                    report TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute(
                "INSERT INTO research_history (query, report, created_at) VALUES (?, ?, ?)",
                (query, final_report, datetime.now())
            )
            conn.commit()
            conn.close()
            st.success("历史记录已保存")
        except Exception as db_e:
            st.warning(f"历史记录存储失败: {db_e}")
        # --- 数据库存储结束 ---
        
        # 显示结果
        display_results(agent, final_report)
        
    except Exception as e:
        st.error(f"研究过程中发生错误: {str(e)}")


def display_results(agent: DeepSearchAgent, final_report: str):
    """显示研究结果"""
    st.header("研究结果")
    
    # 结果标签页
    tab1, tab2, tab3 = st.tabs(["最终报告", "详细信息", "下载"])
    
    with tab1:
        st.markdown(final_report)
    
    with tab2:
        # 段落详情
        st.subheader("段落详情")
        for i, paragraph in enumerate(agent.state.paragraphs):
            with st.expander(f"段落 {i+1}: {paragraph.title}"):
                st.write("**预期内容:**", paragraph.content)
                st.write("**最终内容:**", paragraph.research.latest_summary[:300] + "..." 
                        if len(paragraph.research.latest_summary) > 300 
                        else paragraph.research.latest_summary)
                st.write("**搜索次数:**", paragraph.research.get_search_count())
                st.write("**反思次数:**", paragraph.research.reflection_iteration)
        
        # 搜索历史
        st.subheader("搜索历史")
        all_searches = []
        for paragraph in agent.state.paragraphs:
            all_searches.extend(paragraph.research.search_history)
        
        if all_searches:
            for i, search in enumerate(all_searches):
                with st.expander(f"搜索 {i+1}: {search.query}"):
                    st.write("**URL:**", search.url)
                    st.write("**标题:**", search.title)
                    st.write("**内容预览:**", search.content[:200] + "..." if len(search.content) > 200 else search.content)
                    if search.score:
                        st.write("**相关度评分:**", search.score)
    
    with tab3:
        # 下载选项
        st.subheader("下载报告")
        
        # Markdown下载
        st.download_button(
            label="下载Markdown报告",
            data=final_report,
            file_name=f"deep_search_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
            mime="text/markdown"
        )
        
        # PDF下载
        pdf_bytes, pdf_error = generate_pdf_report(final_report)
        
        st.download_button(
            label="下载PDF报告",
            data=pdf_bytes if pdf_bytes else b"",
            file_name=f"deep_search_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
            mime="application/pdf",
            disabled=pdf_bytes is None
        )
        if pdf_error:
            st.error(f"生成PDF报告失败: {pdf_error}")
        
        # JSON状态下载
        state_json = agent.state.to_json()
        st.download_button(
            label="下载状态文件",
            data=state_json,
            file_name=f"deep_search_state_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json"
        )


if __name__ == "__main__":
    main()
