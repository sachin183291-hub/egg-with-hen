class UserModel {
  final String id;
  final String email;
  final String username;
  final String fullName;
  final String? phone;
  final String role;
  final String? departmentId;
  final bool isActive;
  final bool isVerified;

  const UserModel({
    required this.id,
    required this.email,
    required this.username,
    required this.fullName,
    this.phone,
    required this.role,
    this.departmentId,
    required this.isActive,
    required this.isVerified,
  });

  factory UserModel.fromJson(Map<String, dynamic> json) => UserModel(
    id: json['id'] as String,
    email: json['email'] as String,
    username: json['username'] as String,
    fullName: json['full_name'] as String,
    phone: json['phone'] as String?,
    role: json['role'] as String,
    departmentId: json['department_id'] as String?,
    isActive: json['is_active'] as bool,
    isVerified: json['is_verified'] as bool,
  );

  String get initials {
    final parts = fullName.split(' ');
    if (parts.length >= 2) return '${parts[0][0]}${parts[1][0]}'.toUpperCase();
    return fullName.isNotEmpty ? fullName[0].toUpperCase() : '?';
  }

  bool get isFieldOfficer => role == 'FIELD_OFFICER';
  bool get isAdmin => role == 'SUPER_ADMIN' || role == 'DEPT_ADMIN';
}
