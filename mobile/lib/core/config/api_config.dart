class ApiConfig {
  const ApiConfig({
    required this.appServiceUrl,
    required this.agentServiceUrl,
    required this.timelineServiceUrl,
    required this.crawlerServiceUrl,
  });

  static const _apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost',
  );

  static const current = ApiConfig(
    appServiceUrl: String.fromEnvironment(
      'APP_SERVICE_URL',
      defaultValue: _apiBaseUrl,
    ),
    agentServiceUrl: String.fromEnvironment(
      'AGENT_SERVICE_URL',
      defaultValue: _apiBaseUrl,
    ),
    timelineServiceUrl: String.fromEnvironment(
      'TIMELINE_SERVICE_URL',
      defaultValue: _apiBaseUrl,
    ),
    crawlerServiceUrl: String.fromEnvironment(
      'CRAWLER_SERVICE_URL',
      defaultValue: _apiBaseUrl,
    ),
  );

  final String appServiceUrl;
  final String agentServiceUrl;
  final String timelineServiceUrl;
  final String crawlerServiceUrl;
}
