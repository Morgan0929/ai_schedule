import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../app_scope.dart';
import '../core/utils/date_format.dart';
import '../models/course_item.dart';
import '../models/task_item.dart';
import '../widgets/app_snack_bar.dart';
import '../widgets/course_card.dart';
import '../widgets/task_card.dart';
import 'schedule_import_screen.dart';

class TasksScreen extends StatelessWidget {
  const TasksScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = AppScope.of(context);
    final tasks = state.tasks;
    final courses = state.courses;
    final selectedDate = state.selectedDate;

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: state.refreshTasks,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 88),
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    '${formatDate(selectedDate)} 日程',
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w800,
                        ),
                  ),
                ),
                IconButton(
                  tooltip: '导入课表',
                  onPressed: () async {
                    await Navigator.of(context).push(
                      MaterialPageRoute<void>(
                        builder: (_) => const ScheduleImportScreen(),
                      ),
                    );
                  },
                  icon: const Icon(Icons.download_for_offline_outlined),
                ),
              ],
            ),
            const SizedBox(height: 12),
            OutlinedButton.icon(
              onPressed: state.busy ? null : () => _pickDate(context),
              icon: const Icon(Icons.calendar_month),
              label: Text(formatDate(selectedDate)),
            ),
            const SizedBox(height: 12),
            Text(
              '${tasks.length} 项日程 · ${courses.length} 门课程',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: 10),
            if (state.busy && tasks.isEmpty && courses.isEmpty)
              const Center(
                child: Padding(
                  padding: EdgeInsets.all(32),
                  child: CircularProgressIndicator(),
                ),
              )
            else if (tasks.isEmpty && courses.isEmpty)
              const _EmptyTasks()
            else
              ...courses.map(
                (course) => Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: CourseCard(
                    course: course,
                    mediaBaseUrl: state.config.timelineServiceUrl,
                    mediaToken: state.session?.token,
                    onEdit: () => _editCourse(context, course),
                    onUploadImage: () => _uploadCourseImage(context, course),
                    onDelete: () => _confirmDeleteCourse(context, course),
                  ),
                ),
              ),
            ...tasks.map(
              (task) => Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: TaskCard(
                  task: task,
                  mediaBaseUrl: state.config.timelineServiceUrl,
                  mediaToken: state.session?.token,
                  onEdit: () => _editTask(context, task),
                  onUploadImage: () => _uploadTaskImage(context, task),
                  onComplete: () => _complete(context, task),
                  onDelete: () => _confirmDelete(context, task),
                ),
              ),
            ),
          ],
        ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => showModalBottomSheet<void>(
          context: context,
          isScrollControlled: true,
          builder: (_) => TaskEditorSheet(initialDate: selectedDate),
        ),
        icon: const Icon(Icons.add),
        label: const Text('新建'),
      ),
    );
  }

  Future<void> _confirmDelete(BuildContext context, TaskItem task) async {
    final state = AppScope.of(context);
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('删除日程'),
        content: Text('确定删除「${task.title}」吗？'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('删除'),
          ),
        ],
      ),
    );
    if (confirmed == true) {
      try {
        await state.deleteTask(task);
        if (context.mounted) {
          showSuccessSnackBar(context, '已删除「${task.title}」');
        }
      } catch (_) {
        if (context.mounted) {
          showErrorSnackBar(context, state.error ?? '删除日程失败');
          state.clearError();
        }
      }
    }
  }

  Future<void> _editTask(BuildContext context, TaskItem task) async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (_) => TaskEditorSheet(
        initialDate: task.startTime,
        task: task,
      ),
    );
  }

  Future<void> _uploadTaskImage(BuildContext context, TaskItem task) async {
    final picker = ImagePicker();
    final image = await picker.pickImage(
      source: ImageSource.gallery,
      imageQuality: 88,
    );
    if (image == null) {
      return;
    }
    final state = AppScope.of(context);
    try {
      await state.uploadTaskImage(task, image.path);
      if (context.mounted) {
        showSuccessSnackBar(context, '图片已上传');
      }
    } catch (_) {
      if (context.mounted) {
        showErrorSnackBar(context, state.error ?? '上传图片失败');
        state.clearError();
      }
    }
  }

  Future<void> _confirmDeleteCourse(BuildContext context, CourseItem course) async {
    final state = AppScope.of(context);
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('删除课程'),
        content: Text('确定删除「${course.courseName}」吗？'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('删除'),
          ),
        ],
      ),
    );
    if (confirmed == true) {
      try {
        await state.deleteCourse(course);
        if (context.mounted) {
          showSuccessSnackBar(context, '已删除「${course.courseName}」');
        }
      } catch (_) {
        if (context.mounted) {
          showErrorSnackBar(context, state.error ?? '删除课程失败');
          state.clearError();
        }
      }
    }
  }

  Future<void> _editCourse(BuildContext context, CourseItem course) async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (_) => _EditCourseSheet(course: course),
    );
  }

  Future<void> _uploadCourseImage(BuildContext context, CourseItem course) async {
    final picker = ImagePicker();
    final image = await picker.pickImage(
      source: ImageSource.gallery,
      imageQuality: 88,
    );
    if (image == null) {
      return;
    }
    final state = AppScope.of(context);
    try {
      await state.uploadCourseImage(course, image.path);
      if (context.mounted) {
        showSuccessSnackBar(context, '图片已上传');
      }
    } catch (_) {
      if (context.mounted) {
        showErrorSnackBar(context, state.error ?? '上传图片失败');
        state.clearError();
      }
    }
  }

  Future<void> _complete(BuildContext context, TaskItem task) async {
    final state = AppScope.of(context);
    try {
      await state.completeTask(task);
      if (context.mounted) {
        showSuccessSnackBar(context, '已完成「${task.title}」');
      }
    } catch (_) {
      if (context.mounted) {
        showErrorSnackBar(context, state.error ?? '更新日程失败');
        state.clearError();
      }
    }
  }

  Future<void> _pickDate(BuildContext context) async {
    final state = AppScope.of(context);
    final date = await showDatePicker(
      context: context,
      initialDate: state.selectedDate,
      firstDate: DateTime.now().subtract(const Duration(days: 365)),
      lastDate: DateTime.now().add(const Duration(days: 365 * 2)),
    );
    if (date == null) {
      return;
    }
    try {
      await state.selectDate(date);
    } catch (_) {
      if (context.mounted) {
        showErrorSnackBar(context, state.error ?? '查询日程失败');
        state.clearError();
      }
    }
  }
}

class _EditCourseSheet extends StatefulWidget {
  const _EditCourseSheet({required this.course});

  final CourseItem course;

  @override
  State<_EditCourseSheet> createState() => _EditCourseSheetState();
}

class _EditCourseSheetState extends State<_EditCourseSheet> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _nameController;
  late final TextEditingController _teacherController;
  late final TextEditingController _locationController;
  late final TextEditingController _startSectionController;
  late final TextEditingController _endSectionController;

  @override
  void initState() {
    super.initState();
    final course = widget.course;
    _nameController = TextEditingController(text: course.courseName);
    _teacherController = TextEditingController(text: course.teacher ?? '');
    _locationController = TextEditingController(text: course.location ?? '');
    _startSectionController = TextEditingController(
      text: course.startSection?.toString() ?? '',
    );
    _endSectionController = TextEditingController(
      text: course.endSection?.toString() ?? '',
    );
  }

  @override
  void dispose() {
    _nameController.dispose();
    _teacherController.dispose();
    _locationController.dispose();
    _startSectionController.dispose();
    _endSectionController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final bottom = MediaQuery.of(context).viewInsets.bottom;
    return Padding(
      padding: EdgeInsets.fromLTRB(16, 16, 16, bottom + 16),
      child: Form(
        key: _formKey,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      '编辑课程',
                      style: Theme.of(context).textTheme.titleLarge?.copyWith(
                            fontWeight: FontWeight.w800,
                          ),
                    ),
                  ),
                  IconButton(
                    tooltip: '关闭',
                    onPressed: () => Navigator.of(context).pop(),
                    icon: const Icon(Icons.close),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _nameController,
                decoration: const InputDecoration(
                  labelText: '课程名称',
                  prefixIcon: Icon(Icons.school_outlined),
                ),
                validator: (value) =>
                    value == null || value.trim().isEmpty ? '请输入课程名称' : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _teacherController,
                decoration: const InputDecoration(
                  labelText: '教师',
                  prefixIcon: Icon(Icons.person_outline),
                ),
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _locationController,
                decoration: const InputDecoration(
                  labelText: '地点',
                  prefixIcon: Icon(Icons.place_outlined),
                ),
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: TextFormField(
                      controller: _startSectionController,
                      keyboardType: TextInputType.number,
                      decoration: const InputDecoration(labelText: '开始节次'),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: TextFormField(
                      controller: _endSectionController,
                      keyboardType: TextInputType.number,
                      decoration: const InputDecoration(labelText: '结束节次'),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              FilledButton.icon(
                onPressed: _submit,
                icon: const Icon(Icons.check),
                label: const Text('保存'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) {
      return;
    }
    final startSection = _optionalInt(_startSectionController.text);
    final endSection = _optionalInt(_endSectionController.text);
    if (startSection != null && endSection != null && endSection < startSection) {
      showErrorSnackBar(context, '结束节次不能早于开始节次');
      return;
    }
    final state = AppScope.of(context);
    try {
      await state.updateCourse(
        course: widget.course,
        courseName: _nameController.text.trim(),
        teacher: _teacherController.text.trim(),
        location: _locationController.text.trim(),
        startSection: startSection,
        endSection: endSection,
      );
      if (mounted) {
        Navigator.of(context).pop();
        showSuccessSnackBar(context, '课程已更新');
      }
    } catch (_) {
      if (mounted) {
        showErrorSnackBar(context, state.error ?? '更新课程失败');
        state.clearError();
      }
    }
  }

  int? _optionalInt(String value) {
    final trimmed = value.trim();
    if (trimmed.isEmpty) {
      return null;
    }
    return int.tryParse(trimmed);
  }
}

class TaskEditorSheet extends StatefulWidget {
  const TaskEditorSheet({required this.initialDate, this.task, super.key});

  final DateTime initialDate;
  final TaskItem? task;

  @override
  State<TaskEditorSheet> createState() => _TaskEditorSheetState();
}

class _TaskEditorSheetState extends State<TaskEditorSheet> {
  final _formKey = GlobalKey<FormState>();
  final _titleController = TextEditingController();
  final _descriptionController = TextEditingController();
  final _locationController = TextEditingController();
  late DateTime _start;
  late DateTime _end;
  TaskPriority _priority = TaskPriority.medium;
  TaskCategory _category = TaskCategory.personal;
  String? _imagePath;

  @override
  void initState() {
    super.initState();
    final task = widget.task;
    if (task == null) {
      _start = DateTime(widget.initialDate.year, widget.initialDate.month,
          widget.initialDate.day, 9);
      _end = _start.add(const Duration(hours: 1));
    } else {
      _titleController.text = task.title;
      _descriptionController.text = task.description ?? '';
      _locationController.text = task.location ?? '';
      _start = task.startTime;
      _end = task.endTime;
      _priority = task.priority;
      _category = task.category;
    }
  }

  @override
  void dispose() {
    _titleController.dispose();
    _descriptionController.dispose();
    _locationController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final bottom = MediaQuery.of(context).viewInsets.bottom;
    return Padding(
      padding: EdgeInsets.fromLTRB(16, 16, 16, bottom + 16),
      child: Form(
        key: _formKey,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      widget.task == null ? '新建日程' : '编辑日程',
                      style: Theme.of(context).textTheme.titleLarge?.copyWith(
                            fontWeight: FontWeight.w800,
                          ),
                    ),
                  ),
                  IconButton(
                    tooltip: '关闭',
                    onPressed: () => Navigator.of(context).pop(),
                    icon: const Icon(Icons.close),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _titleController,
                decoration: const InputDecoration(
                  labelText: '标题',
                  prefixIcon: Icon(Icons.event_note),
                ),
                validator: (value) =>
                    value == null || value.trim().isEmpty ? '请输入标题' : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _descriptionController,
                maxLines: 2,
                decoration: const InputDecoration(
                  labelText: '备注',
                  prefixIcon: Icon(Icons.notes),
                ),
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _locationController,
                decoration: const InputDecoration(
                  labelText: '地点',
                  prefixIcon: Icon(Icons.place_outlined),
                ),
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: () => _pickDateTime(isStart: true),
                      icon: const Icon(Icons.play_arrow),
                      label: Text(formatDateTime(_start)),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: () => _pickDateTime(isStart: false),
                      icon: const Icon(Icons.stop),
                      label: Text(formatDateTime(_end)),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              SegmentedButton<TaskPriority>(
                segments: const [
                  ButtonSegment(value: TaskPriority.high, label: Text('高')),
                  ButtonSegment(value: TaskPriority.medium, label: Text('中')),
                  ButtonSegment(value: TaskPriority.low, label: Text('低')),
                ],
                selected: {_priority},
                onSelectionChanged: (value) =>
                    setState(() => _priority = value.first),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<TaskCategory>(
                initialValue: _category,
                decoration: const InputDecoration(
                  labelText: '类型',
                  prefixIcon: Icon(Icons.category_outlined),
                ),
                items: const [
                  DropdownMenuItem(
                      value: TaskCategory.personal, child: Text('个人')),
                  DropdownMenuItem(value: TaskCategory.work, child: Text('工作')),
                  DropdownMenuItem(
                      value: TaskCategory.meeting, child: Text('会议')),
                  DropdownMenuItem(value: TaskCategory.trip, child: Text('出行')),
                ],
                onChanged: (value) {
                  if (value != null) {
                    setState(() => _category = value);
                  }
                },
              ),
              const SizedBox(height: 12),
              OutlinedButton.icon(
                onPressed: _pickImage,
                icon: const Icon(Icons.image_outlined),
                label: Text(_imagePath == null ? '添加图片' : '已选择图片'),
              ),
              const SizedBox(height: 16),
              FilledButton.icon(
                onPressed: _submit,
                icon: const Icon(Icons.check),
                label: const Text('保存'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _pickDateTime({required bool isStart}) async {
    final current = isStart ? _start : _end;
    final date = await showDatePicker(
      context: context,
      initialDate: current,
      firstDate: DateTime.now().subtract(const Duration(days: 365)),
      lastDate: DateTime.now().add(const Duration(days: 365 * 2)),
    );
    if (date == null || !mounted) {
      return;
    }
    final time = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.fromDateTime(current),
    );
    if (time == null) {
      return;
    }
    final selected =
        DateTime(date.year, date.month, date.day, time.hour, time.minute);
    setState(() {
      if (isStart) {
        _start = selected;
        if (!_end.isAfter(_start)) {
          _end = _start.add(const Duration(hours: 1));
        }
      } else {
        _end = selected;
      }
    });
  }

  Future<void> _pickImage() async {
    final picker = ImagePicker();
    final image = await picker.pickImage(
      source: ImageSource.gallery,
      imageQuality: 88,
    );
    if (image == null || !mounted) {
      return;
    }
    setState(() => _imagePath = image.path);
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) {
      return;
    }
    if (!_end.isAfter(_start)) {
      showErrorSnackBar(context, '结束时间必须晚于开始时间');
      return;
    }
    final state = AppScope.of(context);
    try {
      final existing = widget.task;
      TaskItem? saved = existing;
      if (existing == null) {
        saved = await state.createTask(
          title: _titleController.text.trim(),
          description: _descriptionController.text.trim(),
          location: _locationController.text.trim(),
          startTime: _start,
          endTime: _end,
          priority: _priority,
          category: _category,
        );
      } else {
        await state.updateTask(
          task: existing,
          title: _titleController.text.trim(),
          description: _descriptionController.text.trim(),
          location: _locationController.text.trim(),
          startTime: _start,
          endTime: _end,
          priority: _priority,
          category: _category,
        );
      }
      if (_imagePath != null && saved != null) {
        await state.uploadTaskImage(saved, _imagePath!);
      }
      if (mounted) {
        Navigator.of(context).pop();
        showSuccessSnackBar(context, existing == null ? '日程已创建' : '日程已更新');
      }
    } catch (_) {
      if (mounted) {
        showErrorSnackBar(context, state.error ?? '保存日程失败');
        state.clearError();
      }
    }
  }
}

class _EmptyTasks extends StatelessWidget {
  const _EmptyTasks();

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Row(
          children: [
            Icon(Icons.inbox_outlined,
                color: Theme.of(context).colorScheme.primary),
            const SizedBox(width: 12),
            const Expanded(child: Text('还没有日程。')),
          ],
        ),
      ),
    );
  }
}
