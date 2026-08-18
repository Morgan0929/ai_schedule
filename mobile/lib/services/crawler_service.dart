import '../core/api/api_client.dart';
import '../models/schedule_import_result.dart';

class CrawlerService {
  CrawlerService(this.client);

  final ApiClient client;

  Future<ScheduleImportResult> importScheduleFromUrl({
    required int userId,
    required String url,
  }) async {
    final data = await client.post(
      '/api/v1/crawl/schedule/from-url',
      body: {'user_id': userId, 'url': url},
    ) as Map<String, dynamic>;
    return ScheduleImportResult.fromJson(data);
  }

  Future<ScheduleImportResult> importScheduleFromHtml({
    required int userId,
    required String html,
    String? sourceUrl,
  }) async {
    final data = await client.post(
      '/api/v1/crawl/schedule/from-html',
      body: {
        'user_id': userId,
        'html': html,
        'source_url': sourceUrl,
      },
    ) as Map<String, dynamic>;
    return ScheduleImportResult.fromJson(data);
  }
}
