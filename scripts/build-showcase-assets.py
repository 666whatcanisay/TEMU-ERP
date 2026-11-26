"""Build repository-native SVG diagrams. Screenshots are captured separately."""
from pathlib import Path
from html import escape

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/assets/showcase'
OUT.mkdir(parents=True, exist_ok=True)
FONT = "'Segoe UI','Microsoft YaHei',sans-serif"

def text(x,y,value,size=18,color='#213047',weight=400,anchor='start'):
    return f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" fill="{color}" text-anchor="{anchor}">{escape(value)}</text>'

def rect(x,y,w,h,fill='#fff',stroke='#dce4ec',radius=16,dash=False):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}"'+(' stroke-dasharray="7 5"' if dash else '')+'/>'

def arrow(path,color='#8191a4',dash=False):
    return f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2" marker-end="url(#arrow)"'+(' stroke-dasharray="7 5"' if dash else '')+'/>'

def save(name,title,w,h,items):
    svg=f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" role="img" aria-labelledby="title desc"><title id="title">{escape(title)}</title><desc id="desc">项目结构示意图，实线表示已实现的工作台能力，人工平台操作与预留接口另作标识。</desc><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#8191a4"/></marker></defs>{''.join(items)}</svg>'''
    (OUT/name).write_text(svg,encoding='utf-8')

def build():
    a=[rect(1,1,1238,458,'#f7f9fc','#dce4ec',24),rect(1,1,13,458,'#c24e0c','#c24e0c',6),
       text(48,54,'TEMU-ERP',20,'#c24e0c',700),text(1186,54,'PYTHON  /  MYSQL  /  DECIMAL',14,'#627083',500,'end'),
       text(48,124,'全托管选品与买手提报工作台',42,weight=700),
       text(48,170,'选品有来源 · 成本可拆解 · 核价有记录 · 资料可复用',23,'#596c82'),
       rect(48,203,1144,2,'#e1e7ef','#e1e7ef',0)]
    cards=[('01','候选研究','规格、市场参照与来源'),('02','商品与成本','SKU、包装与完整费用'),('03','核价与判断','基准、保守与目标底价'),('04','内部提报','评审资料与反馈重算')]
    for i,(num,title,sub) in enumerate(cards):
        x=48+i*292
        a += [rect(x,238,268,130),text(x+20,271,num,15,'#c24e0c',700),text(x+20,309,title,23,weight=700),text(x+20,341,sub,15,'#627083')]
        if i<3:a.append(arrow(f'M{x+270} 303 H{x+288}'))
    a += [text(48,418,'供货决策与资料准备 MVP',16,'#627083'),text(1190,418,'公开规格 + 明确预算 + 可复核输出',16,'#627083',anchor='end')]
    save('cover.svg','Temu全托管供货决策工作台：选品、成本、核价与内部提报',1240,460,a)

    a=[rect(1,1,1238,478,'#f7f9fc','#dce4ec',24),text(40,48,'业务工作流',26,weight=700),text(40,78,'从一件商品的来源，到一份能解释成本与核价的内部评审资料。',16,'#627083')]
    boxes=[(40,115,'1  候选与证据','商品链接、尺寸、件数','未知销量不补造'),(450,115,'2  SKU与供货资料','材质、组成、包装、货源','平台ID未返回则留空'),(860,115,'3  完整成本与情景','采购、退回、分摊、税费','区分贡献率与净收益'),
           (40,310,'6  重新评估与决定','补资料、议价、降本或暂缓','保留历史记录'),(450,310,'5  登记买手反馈','原话、日期、凭证、SKU核价','平台任务由人工处理'),(860,310,'4  内部评审资料','HTML、JSON及只读填写计划','不是Temu导入模板')]
    for x,y,title,line,note in boxes:
        a += [rect(x,y,340,124),text(x+20,y+34,title,21,weight=700),text(x+20,y+68,line,16,'#596c82'),text(x+20,y+99,note,14,'#c24e0c')]
    a += [arrow('M380 177 H444'),arrow('M790 177 H854'),arrow('M1030 239 V304'),arrow('M860 372 H796'),arrow('M450 372 H386'),arrow('M210 310 V268 H620 V245'),text(642,273,'依据与核价变化后再计算',14,'#627083')]
    save('workflow.svg','候选、SKU、完整成本、内部评审、买手反馈与重新评估',1240,480,a)

    a=[rect(1,1,1238,658,'#f7f9fc','#dce4ec',24),text(40,48,'技术架构与模块边界',26,weight=700),text(40,78,'分层单体：金额逻辑在后端，图表和浮层读取同一份计算明细。',16,'#627083')]
    a += [rect(40,110,1160,80,'#fff4eb','#efc5a8'),text(66,143,'原生前端',21,'#a6400a',700),text(66,172,'候选研究 / 商品提报 / 反馈跟进 · SVG图表 · 费用浮层 · 来源入口',17,'#596c82'),arrow('M620 190 V218')]
    a += [rect(250,224,740,76),text(280,255,'HTTP API + 应用用例',21,weight=700),text(280,282,'校验输入、关联SKU核价、准备状态、记录变更与生成内部资料',16,'#596c82')]
    for x,w,title,sub in [(40,360,'领域逻辑','证据比较 / 数据校验 / Decimal利润'),(440,360,'业务存储','关系实体 / 外键 / 版本化迁移'),(840,360,'已实现适配器','公开读取 / 规则提取 / 内部导出')]:
        a += [rect(x,356,w,94),text(x+22,391,title,21,weight=700),text(x+22,423,sub,15,'#596c82')]
    a += [arrow('M450 300 V327 H220 V350'),arrow('M620 300 V350'),arrow('M790 300 V327 H1020 V350')]
    a += [rect(40,500,1160,114,'#f2f5f8','#aab6c4',16,True),text(66,537,'预留连接：尚未接通',21,'#627083',700),text(66,573,'DSH / DeepSeek · 公司真实类目模板 · Temu只读账号 · 影刀等RPA执行',17,'#627083'),arrow('M1020 450 V494',dash=True),text(40,641,'SQLite仅保留用于旧数据迁移、显式回退和基础测试；本机应用默认使用MySQL。',14,'#627083')]
    save('architecture.svg','前端、HTTP用例、领域逻辑、MySQL和已实现及预留适配器',1240,660,a)
    print('Built cover.svg, workflow.svg and architecture.svg')

if __name__=='__main__':build()
