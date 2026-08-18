class ApiConfig {
  const ApiConfig({
    required this.appServiceUrl,
    required this.agentServiceUrl,
    required this.timelineServiceUrl,
    required this.crawlerServiceUrl,
  });

  static const current = ApiConfig(
    appServiceUrl: String.fromEnvironment(
      'APP_SERVICE_URL',
      defaultValue: 'http://10.0.2.2:8000',
    ),
    agentServiceUrl: String.fromEnvironment(
      'AGENT_SERVICE_URL',
      defaultValue: 'http://10.0.2.2:8002',
    ),
    timelineServiceUrl: String.fromEnvironment(
      'TIMELINE_SERVICE_URL',
      defaultValue: 'http://10.0.2.2:8003',
    ),
    crawlerServiceUrl: String.fromEnvironment(
      'CRAWLER_SERVICE_URL',
      defaultValue: 'http://10.0.2.2:8001',
    ),
  );

  final String appServiceUrl;
  final String agentServiceUrl;
  final String timelineServiceUrl;
  final String crawlerServiceUrl;
}
