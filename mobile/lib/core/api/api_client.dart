import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import 'api_exception.dart';

class ApiClient {
  ApiClient({required this.baseUrl, this.token});

  static const _requestTimeout = Duration(seconds: 45);

  final String baseUrl;
  final String? token;

  Future<dynamic> get(
    String path, {
    Map<String, String?> query = const {},
  }) async {
    final uri = _uri(path, query);
    return _send(() => http.get(uri, headers: _headers()));
  }

  Future<dynamic> post(
    String path, {
    Map<String, String?> query = const {},
    Object? body,
  }) async {
    final uri = _uri(path, query);
    return _send(
      () => http.post(
        uri,
        headers: _headers(),
        body: body == null ? null : jsonEncode(body),
      ),
    );
  }

  Future<dynamic> put(
    String path, {
    Map<String, String?> query = const {},
    Object? body,
  }) async {
    return _send(
      () => http.put(
        _uri(path, query),
        headers: _headers(),
        body: body == null ? null : jsonEncode(body),
      ),
    );
  }

  Future<dynamic> delete(
    String path, {
    Map<String, String?> query = const {},
  }) async {
    return _send(() => http.delete(_uri(path, query), headers: _headers()));
  }

  Future<dynamic> uploadFile(
    String path, {
    Map<String, String?> query = const {},
    required String fieldName,
    required String filePath,
  }) async {
    final request = http.MultipartRequest('POST', _uri(path, query));
    if (token != null && token!.isNotEmpty) {
      request.headers['Authorization'] = 'Bearer $token';
    }
    request.files.add(await http.MultipartFile.fromPath(fieldName, filePath));
    try {
      final streamed = await request.send().timeout(_requestTimeout);
      final response = await http.Response.fromStream(streamed);
      return _decodeResult(response);
    } on TimeoutException {
      throw ApiException('连接后端超时，请确认对应服务已启动');
    } on SocketException {
      throw ApiException('无法连接后端，请确认服务地址和端口可访问');
    } on http.ClientException catch (error) {
      throw ApiException(_networkMessage(error.message));
    }
  }

  Stream<String> postStream(
    String path, {
    Map<String, String?> query = const {},
    Object? body,
  }) async* {
    final request = http.Request('POST', _uri(path, query));
    request.headers.addAll(_headers());
    if (body != null) {
      request.body = jsonEncode(body);
    }
    final client = http.Client();
    try {
      final response = await client.send(request).timeout(_requestTimeout);
      if (response.statusCode < 200 || response.statusCode >= 300) {
        final text = await response.stream.bytesToString();
        throw ApiException(
          text.isEmpty ? '请求失败 (${response.statusCode})' : text,
          statusCode: response.statusCode,
        );
      }
      yield* response.stream.transform(utf8.decoder);
    } on TimeoutException {
      throw ApiException('连接后端超时，请确认对应服务已启动');
    } on SocketException {
      throw ApiException('无法连接后端，请确认服务地址和端口可访问');
    } on http.ClientException catch (error) {
      throw ApiException(_networkMessage(error.message));
    } finally {
      client.close();
    }
  }

  Future<dynamic> _send(Future<http.Response> Function() request) async {
    try {
      final response = await request().timeout(_requestTimeout);
      return _decodeResult(response);
    } on TimeoutException {
      throw ApiException('连接后端超时，请确认对应服务已启动');
    } on SocketException {
      throw ApiException('无法连接后端，请确认服务地址和端口可访问');
    } on http.ClientException catch (error) {
      throw ApiException(_networkMessage(error.message));
    }
  }

  String _networkMessage(String message) {
    if (message.contains('SocketException') ||
        message.contains('Connection timed out') ||
        message.contains('Connection refused')) {
      return '无法连接后端，请确认服务地址和端口可访问';
    }
    return '网络请求失败，请稍后再试';
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
