"""Deterministic DOM semantics extraction."""

from __future__ import annotations

import asyncio
from typing import Any

EXTRACT_JS = """
({ includeFrames, maxElements }) => {
  const selectors = 'a[href],button,input,select,textarea,[role="button"],[role="link"],[role="checkbox"],[role="textbox"],[role="tab"],[role="menuitem"],[role="option"],[role="treeitem"],[tabindex="0"],[onclick],[data-action],main,nav,header,footer,aside,section,article,form,dialog,table,ul,ol,h1,h2,h3,[role="heading"]';
  // CSS selectors for custom web components not exposed to ARIA (e.g. Paddy Power's <abc-button>)
  const customComponentSelectors = '[onclick],[data-action],[tabindex]';
  const STANDARD_TAGS = new Set([
    'a','abbr','address','area','article','aside','audio','b','base','bdi','bdo',
    'blockquote','body','br','button','canvas','caption','cite','code','col','colgroup',
    'data','datalist','dd','del','details','dfn','dialog','div','dl','dt','em','embed',
    'fieldset','figcaption','figure','footer','form','h1','h2','h3','h4','h5','h6',
    'head','header','hgroup','hr','html','i','iframe','img','input','ins','kbd','label',
    'legend','li','link','main','map','mark','menu','meta','meter','nav','noscript',
    'object','ol','optgroup','option','output','p','param','picture','pre','progress',
    'q','rp','rt','ruby','s','samp','script','section','select','slot','small','source',
    'span','strong','style','sub','summary','sup','table','tbody','td','template','textarea',
    'tfoot','th','thead','time','title','tr','track','u','ul','var','video','wbr'
  ]);
  const nodes = [];
  let frameCount = 1;

  const roleOrTag = (el) => el.getAttribute('role') || el.tagName.toLowerCase();

  const isCustomElement = (tag) => tag.includes('-') && !STANDARD_TAGS.has(tag);

  const nameFor = (el, doc) => {
    const aria = el.getAttribute('aria-label');
    if (aria) return aria.trim();
    const labelledBy = el.getAttribute('aria-labelledby');
    if (labelledBy) {
      const labels = labelledBy
        .split(/\\s+/)
        .map((id) => doc.getElementById(id))
        .filter(Boolean);
      const txt = labels.map((l) => l.textContent?.trim() || '').join(' ').trim();
      if (txt) return txt;
    }
    if (el.labels && el.labels.length) {
      const txt = Array.from(el.labels).map((l) => l.textContent?.trim() || '').join(' ').trim();
      if (txt) return txt;
    }
    const ph = el.getAttribute('placeholder');
    if (ph) return ph.trim();
    const txt = el.innerText || el.textContent || '';
    return txt.trim().slice(0, 120);
  };

  const buildCssSelector = (el, doc) => {
    // Build a unique-ish CSS selector for the element.
    if (el.id) return '#' + CSS.escape(el.id);
    const tag = el.tagName.toLowerCase();
    const classes = Array.from(el.classList || [])
      .map((c) => '.' + CSS.escape(c))
      .join('');
    // Try parent path for uniqueness
    let parent = el.parentElement;
    let parentSel = '';
    if (parent) {
      if (parent.id) {
        parentSel = '#' + CSS.escape(parent.id) + ' > ';
      } else {
        const pTag = parent.tagName.toLowerCase();
        const pClasses = Array.from(parent.classList || [])
          .map((c) => '.' + CSS.escape(c))
          .join('');
        if (pClasses) parentSel = pTag + pClasses + ' > ';
      }
    }
    return parentSel + tag + classes;
  };

  const isVisible = (el, view) => {
    const s = view.getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
  };

  const collectFromDoc = (doc, view, frameId) => {
    if (!doc || !view || nodes.length >= maxElements) return;
    const all = Array.from(doc.querySelectorAll(selectors));
    const seen = new Set(all);
    const visible = all.filter((el) => isVisible(el, view));
    for (const el of visible) {
      if (nodes.length >= maxElements) break;
      const tag = el.tagName.toLowerCase();
      const role = roleOrTag(el);
      const name = nameFor(el, doc);
      const type = el.getAttribute('type') || '';
      const id = el.id || '';
      const href = el.getAttribute('href') || '';
      const tabindex = el.getAttribute('tabindex') || '';
      const hasClickHandler = el.hasAttribute('onclick') || el.hasAttribute('data-action');
      const disabled = el.matches(':disabled') || el.getAttribute('aria-disabled') === 'true';
      const checked = el.getAttribute('aria-checked') === 'true' || (tag === 'input' && el.checked === true);
      const expanded = el.getAttribute('aria-expanded');
      const rect = el.getBoundingClientRect();
      const inViewport =
        rect.bottom >= 0 &&
        rect.right >= 0 &&
        rect.top <= (view.innerHeight || 0) &&
        rect.left <= (view.innerWidth || 0);
      const cssSelector = buildCssSelector(el, doc);
      nodes.push({
        dom_index: nodes.length,
        tag,
        role,
        name,
        type,
        id,
        href,
        disabled,
        checked,
        expanded,
        in_viewport: inViewport,
        frame_id: frameId,
        rect: { x: rect.x, y: rect.y, w: rect.width, h: rect.height },
        tabindex,
        has_click_handler: hasClickHandler,
        css_selector: cssSelector,
        text: (el.innerText || '').trim().slice(0, 300),
      });
    }

    // Discover custom web components not in standard ARIA tree
    // (e.g. <abc-button class="btn-odds"> used by Paddy Power)
    const customAll = Array.from(doc.querySelectorAll(customComponentSelectors));
    const customVisible = customAll.filter(
      (el) => !seen.has(el) && isVisible(el, view)
    );
    for (const el of customVisible) {
      if (nodes.length >= maxElements) break;
      const tag = el.tagName.toLowerCase();
      if (!isCustomElement(tag)) continue;
      const role = roleOrTag(el);
      const name = nameFor(el, doc);
      const id = el.id || '';
      const tabindex = el.getAttribute('tabindex') || '';
      const hasClickHandler = el.hasAttribute('onclick') || el.hasAttribute('data-action');
      const disabled = el.getAttribute('aria-disabled') === 'true';
      const rect = el.getBoundingClientRect();
      const inViewport =
        rect.bottom >= 0 &&
        rect.right >= 0 &&
        rect.top <= (view.innerHeight || 0) &&
        rect.left <= (view.innerWidth || 0);
      const cssSelector = buildCssSelector(el, doc);
      nodes.push({
        dom_index: nodes.length,
        tag,
        role,
        name,
        type: '',
        id,
        href: '',
        disabled,
        checked: false,
        expanded: null,
        in_viewport: inViewport,
        frame_id: frameId,
        rect: { x: rect.x, y: rect.y, w: rect.width, h: rect.height },
        tabindex,
        has_click_handler: hasClickHandler,
        css_selector: cssSelector,
        is_custom_element: true,
        text: (el.innerText || '').trim().slice(0, 300),
      });
    }
  };

  const traverseFrames = (rootDoc, rootView, frameIdPrefix) => {
    if (!includeFrames || nodes.length >= maxElements) return;
    const frames = Array.from(rootDoc.querySelectorAll('iframe,frame'));
    for (let idx = 0; idx < frames.length; idx += 1) {
      if (nodes.length >= maxElements) break;
      const frameEl = frames[idx];
      try {
        const childDoc = frameEl.contentDocument;
        const childWin = frameEl.contentWindow;
        if (!childDoc || !childWin) continue;
        frameCount += 1;
        const childFrameId = `${frameIdPrefix}>f${idx}`;
        collectFromDoc(childDoc, childWin, childFrameId);
        traverseFrames(childDoc, childWin, childFrameId);
      } catch (_err) {
        // Cross-origin frames are intentionally skipped.
      }
    }
  };

  collectFromDoc(document, window, 'main');
  traverseFrames(document, window, 'main');

  return {
    title: document.title,
    node_count: nodes.length,
    frame_count: frameCount,
    nodes,
  };
}
"""


async def extract_semantics(page: Any, *, include_frames: bool = True, max_elements: int = 2000) -> dict[str, Any]:
    for attempt in range(1, 4):
        try:
            return await page.evaluate(EXTRACT_JS, {"includeFrames": include_frames, "maxElements": max_elements})
        except Exception as exc:
            msg = str(exc)
            # Navigation races can invalidate execution context mid-evaluate.
            if "Execution context was destroyed" not in msg:
                raise
            if attempt == 3:
                raise
            await asyncio.sleep(0.2 * attempt)
    return await page.evaluate(EXTRACT_JS, {"includeFrames": include_frames, "maxElements": max_elements})
