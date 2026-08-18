class ScheduleImportResult {
  const ScheduleImportResult({
    required this.status,
    required this.message,
    this.courseCount = 0,
    this.menuUrl,
    this.recordId,
  });

  final String status;
  final String message;
  final int courseCount;
  final String? menuUrl;
  final int? recordId;

  bool get imported => status == 'IMPORTED';
  bool get requiresLogin => status == 'LOGIN_REQUIRED';

  factory ScheduleImportResult.fromJson(Map<String, dynamic> json) {
    return ScheduleImportResult(
      status: json['status']?.toString() ?? 'FAILED',
      message: json['message']?.toString() ?? '课表采集失败',
      courseCount: json['course_count'] as int? ?? 0,
      menuUrl: json['menu_url']?.toString(),
      recordId: json['record_id'] as int?,
    );
  }
}
