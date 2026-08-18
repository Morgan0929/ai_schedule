import '../core/api/api_client.dart';
import '../models/todo_item.dart';

class TodoService {
  TodoService(this.client);

  final ApiClient client;

  Future<List<TodoItem>> listTodos({required int userId}) async {
    final data = await client.get(
      '/api/v1/todos',
      query: {'user_id': userId.toString()},
    ) as List<dynamic>;
    return data
        .whereType<Map<String, dynamic>>()
        .map(TodoItem.fromJson)
        .toList();
  }

  Future<List<TodoItem>> listTodoHistory({required int userId}) async {
    final data = await client.get(
      '/api/v1/todos/history',
      query: {'user_id': userId.toString()},
    ) as List<dynamic>;
    return data
        .whereType<Map<String, dynamic>>()
        .map(TodoItem.fromJson)
        .toList();
  }

  Future<void> completeTodo({required int userId, required int todoId}) async {
    await client.put(
      '/api/v1/todos/$todoId/done',
      query: {'user_id': userId.toString()},
    );
  }
}
