String twoDigits(int value) => value.toString().padLeft(2, '0');

String formatDate(DateTime value) {
  return '${value.year}-${twoDigits(value.month)}-${twoDigits(value.day)}';
}

String formatClock(DateTime value) {
  return '${twoDigits(value.hour)}:${twoDigits(value.minute)}';
}

String formatDateTime(DateTime value) {
  return '${formatDate(value)} ${formatClock(value)}';
}

String formatDurationRange(DateTime start, DateTime end) {
  if (start.year == end.year && start.month == end.month && start.day == end.day) {
    return '${formatDate(start)} ${formatClock(start)}-${formatClock(end)}';
  }
  return '${formatDateTime(start)} - ${formatDateTime(end)}';
}
