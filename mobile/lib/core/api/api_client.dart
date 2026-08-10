import 'dart:convert';

import 'package:http/http.dart' as http;

import 'api_exception.dart';

class ApiClient {
  ApiClient({required this.baseUrl, this.token});

  final String baseUrl;
  final String? token;

  Future<dynamic> get(
    String path, {
    Map<String, String?> query = const {},
  }) async {
    final uri = _uri(path, query);
    final response = await http.get(uri, headers: _headers());
    return _decodeResult(response);
  }

  Future<dynamic> post(
    String path, {
    Map<String, String?> query = const {},
    Object? body,
  }) async {
    final uri = _uri(path, query);
    final response = await http.post(
      uri,
      headers: _headers(),
      body: body == null ? null : jsonEncode(body),
    );
    return _decodeResult(response);
  }

  Future<dynamic> put(String path, {Object? body}) async {
    final response = await http.put(
      _uri(path),
      headers: _headers(),
      body: body == null ? null : jsonEncode(body),
    );
    return _decodeResult(response);
  }

  Future<dynamic> delete(String path) async {
    final response = await http.delete(_uri(path), headers: _headers());
    return _decodeResult(response);
  }

  Uri _uri(String path, [Map<String, String?> query = const {}]) {
    final cleanBase = baseUrl.endsWith('/')
        ? baseUrl.substring(0, baseUrl.length - 1)
        : baseUrl;
    final cleanPath = path.startsWith('/') ? path : '/$path';
    final uri = Uri.parse('$cleanBase$cleanPath');
    final filtered = <String, String>{};
    for (final entry in query.entries) {
      if (entry.value != null && entry.value!.isNotEmpty) {
        filtered[entry.key] = entry.value!;
      }
    }
    return filtered.isEmpty ? uri : uri.replace(queryParameters: filtered);
  }

  Map<String, String> _headers() {
    return {
      'Content-Type': 'application/json',
      if (token != null && token!.isNotEmpty) 'Authorization': 'Bearer $token',
    };
  }

  dynamic _decodeResult(http.Response response) {
    dynamic payload;
    try {
      payload = response.body.isEmpty ? null : jsonDecode(response.body);
    } on FormatException {
      throw ApiException('服务返回了无法解析的数据', statusCode: response.statusCode);
    }

    if (response.statusCode < 200 || response.statusCode >= 300) {
      final message = payload is Map<String, dynamic>
          ? payload['message']?.toString()
          : null;
      throw ApiException(message ?? '请求失败 (${response.statusCode})',
          statusCode: response.statusCode);
    }

    if (payload is Map<String, dynamic> && payload.containsKey('code')) {
      final code = payload['code'];
      if (code != 200 && code != 201) {
        throw ApiException(payload['message']?.toString() ?? '请求失败');
      }
      return payload['data'];
    }

    return payload;
  }
}
