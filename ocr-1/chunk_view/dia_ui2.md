# 任务:详情面板 diff 改成"逐字高亮"(只动这一处)
发之前把 ‎`escapeHtml` 那句按它项目里实际的转义函数名提一下(它自己应该有);其余照搬即可。
## 范围(严格)
只改 chunk 详情面板里渲染「文本」和「结构化」两栏内容的部分,把现在的"整块高亮"换成"逐字 diff 高亮"。
**不要动**:数据来源、接口、布局、文件清单、左右对比列表、元数据标签页(它按字段高亮即可,保持现状)。

## 做法
1. 加这几个工具函数(逐字 LCS diff;CJK 按字符比对):
```js
function dpush(out,t,ch){if(out.length&&out[out.length-1].t===t)out[out.length-1].s+=ch;else out.push({t,s:ch});}
function diffTokens(a,b){const A=[...a],B=[...b],n=A.length,m=B.length;
  if(n*m>400000)return null; // 太长回退整块高亮,防卡
  const dp=Array.from({length:n+1},()=>new Int32Array(m+1));
  for(let i=n-1;i>=0;i--)for(let j=m-1;j>=0;j--)dp[i][j]=A[i]===B[j]?dp[i+1][j+1]+1:Math.max(dp[i+1][j],dp[i][j+1]);
  const out=[];let i=0,j=0;
  while(i<n&&j<m){if(A[i]===B[j]){dpush(out,'eq',A[i]);i++;j++;}else if(dp[i+1][j]>=dp[i][j+1]){dpush(out,'del',A[i]);i++;}else{dpush(out,'ins',B[j]);j++;}}
  while(i<n){dpush(out,'del',A[i]);i++;}while(j<m){dpush(out,'ins',B[j]);j++;}
  return out;
}
// side='L'(当前切法栏)只标红删除;side='R'(新参数栏)只标绿新增;相同不标
function renderInline(diff,side){return diff.map(s=>s.t==='eq'?escapeHtml(s.s):(s.t==='del'&&side==='L')?'<span class="d-del">'+escapeHtml(s.s)+'</span>':(s.t==='ins'&&side==='R')?'<span class="d-ins">'+escapeHtml(s.s)+'</span>':'').join('');}
```
(`escapeHtml` 用你项目里已有的转义函数;没有就加一个把 `<`&`>` 转义的。)

2. 渲染两栏时:拿**当前切法**那版文本和**新参数**那版文本,调用一次 `diffTokens(当前文本, 新文本)`;**左栏**用 `renderInline(diff,'L')`、**右栏**用 `renderInline(diff,'R')` 填充。结构化(JSON)那栏同样处理。
3. 若 `diffTokens` 返回 null(文本过长),回退到现在的整块高亮即可。
4. 只有一侧存在的块(新增/消失)按现状展示,不做逐字 diff。

## CSS(加两条)
```css
.d-del{background:#fde2e2;color:#9a2b2b;border-radius:2px;}
.d-ins{background:#dff5e4;color:#1c7d35;border-radius:2px;}
```

## 保持不变
数据来源、接口、布局、其它标签页、左右对比列表,全部不动。只替换"文本/结构化"两栏的高亮方式。

## 验收
- 打开一个有变化的 chunk:文本/结构化两栏里,**改动的字**精确标色(左红右绿),相同文字不标。
- 两侧完全一致的块:不出现任何高亮。
- 超长文本不卡(走回退)。
- 其它功能、接口无变化。
