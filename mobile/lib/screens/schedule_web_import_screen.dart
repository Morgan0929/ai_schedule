import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';

import '../app_scope.dart';
import '../models/schedule_import_result.dart';
import '../widgets/app_snack_bar.dart';

class ScheduleWebImportScreen extends StatefulWidget {
  const ScheduleWebImportScreen({required this.initialUrl, super.key});

  final String initialUrl;

  @override
  State<ScheduleWebImportScreen> createState() =>
      _ScheduleWebImportScreenState();
}

class _ScheduleWebImportScreenState extends State<ScheduleWebImportScreen> {
  late final WebViewController _controller;
  bool _loading = true;
  bool _importing = false;
  bool _autoImported = false;
  bool _autoOpenedScheduleEntry = false;
  ScheduleImportResult? _result;
  String _currentUrl = '';

  @override
  void initState() {
    super.initState();
    final uri = Uri.tryParse(widget.initialUrl);
    final startUrl = uri != null && uri.hasScheme && uri.hasAuthority
        ? uri
        : Uri.parse('https://jxfw.gdut.edu.cn/login!welcome.action');
    _currentUrl = startUrl.toString();
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setNavigationDelegate(
        NavigationDelegate(
          onPageStarted: (url) {
            setState(() {
              _loading = true;
              _currentUrl = url;
            });
          },
          onPageFinished: (url) {
            setState(() {
              _loading = false;
              _currentUrl = url;
            });
            _installPageProbe();
            Future<void>.delayed(const Duration(milliseconds: 900), () {
              if (mounted) {
                _tryAutoImport();
              }
            });
          },
        ),
      )
      ..loadRequest(startUrl);
  }

  @override
  Widget build(BuildContext context) {
    final state = AppScope.of(context);
    return Scaffold(
      appBar: AppBar(
        title: const Text('网页登录导入'),
        actions: [
          TextButton(
            onPressed: () => _controller.reload(),
            child: const Text('刷新'),
          ),
          TextButton(
            onPressed: () async {
              if (await _controller.canGoBack()) {
                await _controller.goBack();
              }
            },
            child: const Text('返回'),
          ),
        ],
      ),
      body: Column(
        children: [
          LinearProgressIndicator(value: _loading ? null : 1),
          Expanded(child: WebViewWidget(controller: _controller)),
          if (_result != null) _ImportStatus(result: _result!),
          SafeArea(
            top: false,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(12, 10, 12, 12),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      _currentUrl,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ),
                  const SizedBox(width: 10),
                  FilledButton(
                    onPressed: state.busy || _loading || _importing
                        ? null
                        : _importCurrentPage,
                    child: state.busy || _importing
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Text('导入当前页'),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _importCurrentPage() async {
    await _importCurrentPageHtml();
  }

  Future<ScheduleImportResult?> _importCurrentPageHtml({
    bool showErrors = true,
  }) async {
    if (_importing) {
      return null;
    }
    final state = AppScope.of(context);
    setState(() => _importing = true);
    try {
      final html = await _readHtml();
      final result = await state.importScheduleFromHtml(
        html: html,
        sourceUrl: _currentUrl,
      );
      if (!mounted) {
        return null;
      }
      if (result.imported || showErrors) {
        setState(() => _result = result);
      }
      if (result.imported) {
        showSuccessSnackBar(context, '已导入 ${result.courseCount} 门课程');
      } else if (showErrors) {
        showErrorSnackBar(context, result.message);
      }
      return result;
    } catch (_) {
      if (mounted && showErrors) {
        showErrorSnackBar(context, state.error ?? '导入当前页失败');
        state.clearError();
      }
      return null;
    } finally {
      if (mounted) {
        setState(() => _importing = false);
      }
    }
  }

  Future<void> _tryAutoImport() async {
    if (_autoImported || _importing || !mounted) {
      return;
    }
    final looksReady = await _looksLikeSchedulePage().catchError((_) => false);
    if (!mounted) {
      return;
    }
    if (looksReady) {
      final result = await _importCurrentPageHtml(showErrors: false);
      if (result?.imported == true) {
        _autoImported = true;
      }
      return;
    }
    if (!_autoOpenedScheduleEntry) {
      final opened = await _openScheduleEntry().catchError((_) => false);
      if (opened == true && mounted) {
        _autoOpenedScheduleEntry = true;
        Future<void>.delayed(const Duration(milliseconds: 1400), () {
          if (mounted) {
            _tryAutoImport();
          }
        });
      }
    }
  }

  Future<bool> _openScheduleEntry() async {
    final result = await _controller.runJavaScriptReturningResult(r'''
(() => {
  const scheduleWords = [
    '我的课表', '个人课表', '学生课表', '课程表', '课表查询', '课程查询', '我的课程', '班级课表'
  ];
  const avoidWords = ['全校课表', '考试', '成绩', '培养方案', '学籍', '考勤'];
  const roots = [];
  const addDoc = (doc, depth = 0) => {
    if (!doc || roots.includes(doc) || depth > 3) return;
    roots.push(doc);
    for (const frame of doc.querySelectorAll('iframe, frame')) {
      try {
        addDoc(frame.contentDocument || frame.contentWindow.document, depth + 1);
      } catch (_) {}
    }
  };
  const textOf = (el) => [
    el.innerText, el.textContent, el.getAttribute('title'), el.getAttribute('aria-label'),
    el.getAttribute('value'), el.id, el.className
  ].filter(Boolean).join(' ').replace(/\s+/g, ' ').trim();
  const visible = (el) => {
    const rect = el.getBoundingClientRect();
    const style = el.ownerDocument.defaultView.getComputedStyle(el);
    return rect.width > 1 && rect.height > 1 && style.display !== 'none' && style.visibility !== 'hidden';
  };
  const clickableFor = (el) => el.closest(
    'a,button,input,[role="button"],[onclick],[class*="x-tree"],[class*="tree"],[class*="menu"],[class*="btn"],[class*="tab"]'
  ) || el;
  const scoreFor = (text) => {
    if (!text) return 0;
    let score = 0;
    scheduleWords.forEach((word, index) => {
      if (text.includes(word)) score += 100 - index * 4;
    });
    avoidWords.forEach((word) => {
      if (text.includes(word)) score -= 70;
    });
    if (/课表|课程/.test(text)) score += 20;
    return score;
  };
  addDoc(document);
  const candidates = [];
  for (const doc of roots) {
    for (const el of doc.querySelectorAll('a,button,input,span,div,li,td,[role="button"],[onclick]')) {
      const text = textOf(el);
      const score = scoreFor(text);
      if (score <= 0 || !visible(el)) continue;
      const clickable = clickableFor(el);
      candidates.push({ el: clickable, text, score });
    }
  }
  candidates.sort((a, b) => b.score - a.score || a.text.length - b.text.length);
  const target = candidates[0]?.el;
  if (!target) return false;
  target.scrollIntoView({ block: 'center', inline: 'center' });
  for (const type of ['pointerdown', 'mousedown', 'mouseup', 'click']) {
    target.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: target.ownerDocument.defaultView }));
  }
  if (typeof target.click === 'function') target.click();
  return true;
})()
''');
    return result == true || result.toString() == 'true';
  }

  Future<void> _installPageProbe() async {
    await _controller.runJavaScript(r'''
(() => {
  if (window.__codexProbeInstalled) return;
  window.__codexProbeInstalled = true;
  window.__codexNetworkLog = window.__codexNetworkLog || [];
  const interesting = /课表|课程|教室|教师|上课|schedule|course|kcb|jskb|xskb|KCMC|JASMC|XQJ|SKJC|SKZC/i;
  const pushLog = (entry) => {
    try {
      const text = [entry.url, entry.body, entry.response].filter(Boolean).join('\n');
      if (!interesting.test(text)) return;
      window.__codexNetworkLog.push({
        time: Date.now(),
        url: String(entry.url || '').slice(0, 1000),
        method: entry.method || '',
        status: entry.status || null,
        response: String(entry.response || '').slice(0, 60000),
      });
      if (window.__codexNetworkLog.length > 30) window.__codexNetworkLog.shift();
    } catch (_) {}
  };
  if (window.fetch) {
    const rawFetch = window.fetch.bind(window);
    window.fetch = (...args) => rawFetch(...args).then((response) => {
      try {
        const cloned = response.clone();
        cloned.text().then((text) => pushLog({
          url: args[0] && (args[0].url || args[0]),
          method: args[1]?.method || 'GET',
          status: response.status,
          response: text,
        })).catch(() => {});
      } catch (_) {}
      return response;
    });
  }
  if (window.XMLHttpRequest) {
    const rawOpen = XMLHttpRequest.prototype.open;
    const rawSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function(method, url) {
      this.__codexMethod = method;
      this.__codexUrl = url;
      return rawOpen.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function(body) {
      this.addEventListener('load', function() {
        pushLog({
          url: this.__codexUrl,
          method: this.__codexMethod,
          status: this.status,
          body,
          response: this.responseText,
        });
      });
      return rawSend.apply(this, arguments);
    };
  }
})()
''').catchError((_) {});
  }

  Future<bool> _looksLikeSchedulePage() async {
    final result = await _controller.runJavaScriptReturningResult(r'''
(() => {
  const roots = [];
  const addDoc = (doc, depth = 0) => {
    if (!doc || roots.includes(doc) || depth > 3) return;
    roots.push(doc);
    for (const frame of doc.querySelectorAll('iframe, frame')) {
      try {
        addDoc(frame.contentDocument || frame.contentWindow.document, depth + 1);
      } catch (_) {}
    }
  };
  addDoc(document);
  let text = '';
  let tableRows = 0;
  let visualCourses = 0;
  let hasLogin = false;
  for (const doc of roots) {
    text += '\n' + (doc.body ? doc.body.innerText : '');
    tableRows += doc.querySelectorAll('table tr').length;
    hasLogin = hasLogin || doc.querySelector('input[type="password"]') !== null;
    for (const node of doc.querySelectorAll('td, th, div, span')) {
      const nodeText = (node.innerText || '').trim();
      if (nodeText.length >= 6 && nodeText.length <= 180 && /(教[-\s]*\d+|实验|校区|室|楼|馆)/.test(nodeText)) {
        const rect = node.getBoundingClientRect();
        if (rect.width >= 20 && rect.height >= 12) visualCourses += 1;
      }
    }
  }
  const hasScheduleWord = /课表|课程表|课程名称|上课地点|教室|学期|周次/.test(text);
  return hasScheduleWord && (tableRows >= 2 || visualCourses >= 1) && !hasLogin;
})()
''');
    return result == true || result.toString() == 'true';
  }

  Future<String> _readHtml() async {
    final result = await _controller.runJavaScriptReturningResult(r'''
(() => {
  const escapeHtml = (value) => String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/`/g, '&#96;');
  const parts = [];
  const addVisibleText = (text) => {
    if (!text) return;
    const pre = document.createElement('pre');
    pre.setAttribute('data-codex-visible-text', 'true');
    pre.textContent = text;
    parts.push(pre.outerHTML);
  };
  const addClickableControls = (rootDoc) => {
    const rows = Array.from(rootDoc.querySelectorAll('a,button,input,[role="button"],[onclick],span,div,li'))
      .map((node) => {
        const text = [node.innerText, node.textContent, node.getAttribute('title'), node.getAttribute('aria-label'), node.getAttribute('value'), node.id, node.className]
          .filter(Boolean).join(' ').replace(/\s+/g, ' ').trim();
        if (!/课表|课程|查询|我的/.test(text)) return '';
        const rect = node.getBoundingClientRect();
        if (!rect || rect.width < 1 || rect.height < 1) return '';
        return `<tr><td>${Math.round(rect.top)}</td><td>${Math.round(rect.left)}</td><td>${escapeHtml(text)}</td></tr>`;
      })
      .filter(Boolean)
      .slice(0, 80)
      .join('');
    if (rows) {
      parts.push(`<table data-codex-clickable-controls="true"><tr><th>top</th><th>left</th><th>text</th></tr>${rows}</table>`);
    }
  };
  const addStateCourses = (rootDoc) => {
    const rows = [];
    const seenRows = new Set();
    const seenObjects = new WeakSet();
    const textKeys = ['course_name', 'coursename', 'kcmc', 'kcm', 'name', 'title', '课程名称', '课程名'];
    const teacherKeys = ['teacher', 'teachername', 'xm', 'skjs', 'jsgxm', '教师', '老师', '授课教师'];
    const locationKeys = ['location', 'classroom', 'jsmc', 'jasmc', 'cdmc', 'room', '教室', '地点', '上课地点'];
    const weekdayKeys = ['week_day', 'weekday', 'xqj', 'day', 'skxq', '星期', '周几'];
    const sectionKeys = ['section', 'sections', 'start_section', 'skjc', 'jc', 'jcs', '节次', '上课节次'];
    const weekKeys = ['week', 'weeks', 'start_week', 'end_week', 'skzc', 'zcd', 'zc', '周次', '上课周次'];
    const keyMatch = (key, keys) => keys.some((item) => String(key).toLowerCase().includes(item.toLowerCase()));
    const valueFor = (obj, keys) => {
      for (const [key, value] of Object.entries(obj)) {
        if (value == null) continue;
        if (keyMatch(key, keys) && typeof value !== 'object') return String(value).trim();
      }
      return '';
    };
    const plainText = (obj) => {
      try {
        return JSON.stringify(obj).slice(0, 3000);
      } catch (_) {
        return String(obj || '');
      }
    };
    const addCandidate = (obj, source) => {
      if (!obj || typeof obj !== 'object' || rows.length >= 500) return;
      const text = plainText(obj);
      if (!/(课|课程|教室|教师|上课|教[-\s]*\d+|KCMC|JASMC|XQJ|SKJC|SKZC)/i.test(text)) return;
      let name = valueFor(obj, textKeys);
      const teacher = valueFor(obj, teacherKeys);
      const location = valueFor(obj, locationKeys);
      const weekday = valueFor(obj, weekdayKeys);
      const section = valueFor(obj, sectionKeys);
      const week = valueFor(obj, weekKeys);
      if (!name) {
        const match = text.match(/(?:课程名称|课程名|kcmc|KCMC|courseName|name)["'=:：\s]+([^,"'，。;；<>{}]{2,40})/i);
        name = match ? match[1].trim() : '';
      }
      if (!name || !/(教[-\s]*\d+|实验|校区|室|楼|馆|JASMC|jsmc|cdmc)/i.test(`${location}\n${text}`)) return;
      const key = [name, teacher, location, weekday, section, week].join('|');
      if (seenRows.has(key)) return;
      seenRows.add(key);
      rows.push(`<tr><td>${escapeHtml(name)}</td><td>${escapeHtml(teacher)}</td><td>${escapeHtml(weekday)}</td><td>${escapeHtml(section)}</td><td>${escapeHtml(week)}</td><td>${escapeHtml(location)}</td><td>${escapeHtml(source)}</td></tr>`);
    };
    const visit = (value, source, depth = 0) => {
      if (value == null || rows.length >= 500 || depth > 5) return;
      if (typeof value === 'string') {
        const trimmed = value.trim();
        if (!trimmed || trimmed.length > 60000 || !/(课|课程|教室|教师|KCMC|JASMC|XQJ|SKJC|SKZC)/i.test(trimmed)) return;
        try {
          visit(JSON.parse(trimmed), source, depth + 1);
        } catch (_) {}
        return;
      }
      if (typeof value !== 'object') return;
      if (value.nodeType || value === rootDoc.defaultView || value === rootDoc) return;
      if (seenObjects.has(value)) return;
      seenObjects.add(value);
      if (Array.isArray(value)) {
        value.slice(0, 2000).forEach((item) => visit(item, source, depth + 1));
        return;
      }
      addCandidate(value, source);
      for (const [key, child] of Object.entries(value).slice(0, 200)) {
        if (!/(课|课程|教室|教师|course|schedule|kcb|jskb|xskb|kc|rows|data|list|KCMC|JASMC|XQJ|SKJC|SKZC)/i.test(`${key} ${plainText(child).slice(0, 500)}`)) continue;
        visit(child, `${source}.${key}`, depth + 1);
      }
    };
    try {
      const win = rootDoc.defaultView;
      if (win.__codexNetworkLog) visit(win.__codexNetworkLog, 'network');
      for (const storage of [win.localStorage, win.sessionStorage]) {
        if (!storage) continue;
        for (let i = 0; i < storage.length; i += 1) {
          const key = storage.key(i);
          visit(storage.getItem(key), `storage.${key}`);
        }
      }
      if (win.jQuery) {
        win.jQuery(rootDoc).find('[id*=kc],[id*=Kb],[id*=kb],[class*=course],[class*=schedule],[class*=panel],[class*=datagrid],table,div').each((_, el) => {
          try { visit(win.jQuery.data(el), `jquery.${el.id || el.className || el.tagName}`); } catch (_) {}
        });
      }
      for (const key of Object.keys(win).slice(0, 3000)) {
        if (!/(课|课程|course|schedule|kcb|jskb|xskb|kc|kb|grid|datagrid|KCMC|JASMC|XQJ|SKJC|SKZC)/i.test(key)) continue;
        try { visit(win[key], `window.${key}`); } catch (_) {}
      }
    } catch (_) {}
    if (rows.length) {
      parts.push(`<table data-codex-state-courses="true"><tr><th>课程名称</th><th>教师</th><th>星期</th><th>节次</th><th>周次</th><th>教室</th><th>source</th></tr>${rows.join('')}</table>`);
    }
  };
  const addVisualSchedule = (rootDoc) => {
    const items = [];
    const headers = [];
    const courseSignal = /(教[-\s]*\d+|实验|校区|室|楼|馆)/;
    const headerSignal = /^(?:[一二三四五六日天]|周[一二三四五六日天]|星期[一二三四五六日天])\s*(?:\d{1,2}[/-]\d{1,2})?$|^\d{1,2}[/-]\d{1,2}$|^第?\d{1,2}(?:-\d{1,2})?节$/;
    const nodes = Array.from(rootDoc.querySelectorAll('td, th, div, span'));
    for (const node of nodes) {
      const text = (node.innerText || '').trim();
      const rect = node.getBoundingClientRect();
      if (!rect || rect.width < 20 || rect.height < 12) continue;
      const normalizedText = text.replace(/\s+/g, ' ');
      if (headerSignal.test(normalizedText)) {
        headers.push({
          text,
          left: Math.round(rect.left),
          top: Math.round(rect.top),
          width: Math.round(rect.width),
          height: Math.round(rect.height),
        });
      }
      if (!text || text.length < 6 || text.length > 220) continue;
      if (headerSignal.test(normalizedText)) continue;
      if (!courseSignal.test(text)) continue;
      const hasCourseChild = Array.from(node.children).some((child) => {
        const childText = (child.innerText || '').trim();
        return childText && childText !== text && courseSignal.test(childText);
      });
      if (hasCourseChild) continue;
      items.push({
        text,
        left: Math.round(rect.left),
        top: Math.round(rect.top),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
      });
    }
    if (!items.length) return;
    const seen = new Set();
    const rows = items
      .filter((item) => {
        const key = `${item.text}|${item.left}|${item.top}`;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      })
      .sort((a, b) => a.top - b.top || a.left - b.left)
      .map((item) => {
        return `<tr><td>${item.top}</td><td>${item.left}</td><td>${item.width}</td><td>${item.height}</td><td>${escapeHtml(item.text)}</td></tr>`;
      })
      .join('');
    parts.push(`<table data-codex-visual-courses="true"><tr><th>top</th><th>left</th><th>width</th><th>height</th><th>课程</th></tr>${rows}</table>`);
    const headerRows = headers
      .filter((item, index, all) => all.findIndex((other) => other.text === item.text && other.left === item.left && other.top === item.top) === index)
      .sort((a, b) => a.top - b.top || a.left - b.left)
      .map((item) => `<tr><td>${item.top}</td><td>${item.left}</td><td>${item.width}</td><td>${item.height}</td><td>${escapeHtml(item.text)}</td></tr>`)
      .join('');
    if (headerRows) {
      parts.push(`<table data-codex-visual-headers="true"><tr><th>top</th><th>left</th><th>width</th><th>height</th><th>text</th></tr>${headerRows}</table>`);
    }
  };
  const addDoc = (doc, depth = 0) => {
    if (!doc || !doc.documentElement || depth > 3) return;
    parts.push(doc.documentElement.outerHTML);
    if (doc.body && doc.body.innerText) {
      addVisibleText(doc.body.innerText);
      addClickableControls(doc);
      addStateCourses(doc);
      addVisualSchedule(doc);
    }
    for (const frame of doc.querySelectorAll('iframe, frame')) {
      try {
        addDoc(frame.contentDocument || frame.contentWindow.document, depth + 1);
      } catch (_) {}
    }
  };
  addDoc(document);
  return parts.join('\n');
})()
''');
    Object decoded = result;
    for (var i = 0; i < 3; i += 1) {
      if (decoded is! String) {
        break;
      }
      final value = decoded.trim();
      if (!value.startsWith('"')) {
        break;
      }
      try {
        decoded = jsonDecode(value);
      } on FormatException {
        break;
      }
    }
    return decoded.toString();
  }
}

class _ImportStatus extends StatelessWidget {
  const _ImportStatus({required this.result});

  final ScheduleImportResult result;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final color =
        result.imported ? scheme.primaryContainer : scheme.errorContainer;
    final foreground =
        result.imported ? scheme.onPrimaryContainer : scheme.onErrorContainer;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      color: color,
      child: Text(
        result.recordId == null
            ? result.message
            : '${result.message} 日志ID: ${result.recordId}',
        maxLines: 2,
        overflow: TextOverflow.ellipsis,
        style: TextStyle(color: foreground),
      ),
    );
  }
}
