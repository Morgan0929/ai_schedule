class CourseItem {
  const CourseItem({
    required this.id,
    required this.courseName,
    required this.weekDay,
    this.teacher,
    this.location,
    this.startTime,
    this.endTime,
    this.startSection,
    this.endSection,
    this.attachments = const [],
  });

  final int id;
  final String courseName;
  final int weekDay;
  final String? teacher;
  final String? location;
  final String? startTime;
  final String? endTime;
  final int? startSection;
  final int? endSection;
  final List<CourseAttachment> attachments;

  String get timeLabel {
    if (startTime != null && startTime!.isNotEmpty) {
      final start = _firstFive(startTime!);
      if (endTime != null && endTime!.isNotEmpty) {
        final end = _firstFive(endTime!);
        return '$start-$end';
      }
      return start;
    }
    if (startSection != null) {
      return endSection != null && endSection != startSection
          ? '第$startSection-$endSection节'
          : '第$startSection节';
    }
    return '时间待确认';
  }

  static String _firstFive(String value) {
    return value.length <= 5 ? value : value.substring(0, 5);
  }

  factory CourseItem.fromJson(Map<String, dynamic> json) {
    return CourseItem(
      id: json['id'] as int,
      courseName: json['course_name']?.toString() ?? '',
      weekDay: json['week_day'] as int? ?? 1,
      teacher: json['teacher']?.toString(),
      location: json['location']?.toString(),
      startTime: json['start_time']?.toString(),
      endTime: json['end_time']?.toString(),
      startSection: json['start_section'] as int?,
      endSection: json['end_section'] as int?,
      attachments: (json['attachments'] as List<dynamic>? ?? const [])
          .whereType<Map<String, dynamic>>()
          .map(CourseAttachment.fromJson)
          .toList(),
    );
  }
}

class CourseAttachment {
  const CourseAttachment({
    required this.id,
    required this.fileUrl,
    required this.contentType,
    required this.fileSize,
    this.originalName,
  });

  final int id;
  final String fileUrl;
  final String contentType;
  final int fileSize;
  final String? originalName;

  factory CourseAttachment.fromJson(Map<String, dynamic> json) {
    return CourseAttachment(
      id: json['id'] as int,
      fileUrl: json['file_url']?.toString() ?? '',
      contentType: json['content_type']?.toString() ?? '',
      fileSize: json['file_size'] as int? ?? 0,
      originalName: json['original_name']?.toString(),
    );
  }
}
