import 'package:flutter/material.dart';

import 'app_colors.dart';

/// Thème global de l'application (Material 3, Dark Mode).
class AppTheme {
  AppTheme._();

  static ThemeData get dark {
    final base = ThemeData.dark(useMaterial3: true);

    final colorScheme = const ColorScheme.dark(
      primary: AppColors.primaryBlue,
      secondary: AppColors.orange,
      surface: AppColors.card,
      error: AppColors.red,
      onPrimary: AppColors.white,
      onSecondary: AppColors.white,
      onSurface: AppColors.white,
    );

    return base.copyWith(
      scaffoldBackgroundColor: AppColors.background,
      colorScheme: colorScheme,
      textTheme: _textTheme(base.textTheme),
      appBarTheme: const AppBarTheme(
        backgroundColor: Colors.transparent,
        elevation: 0,
        foregroundColor: AppColors.white,
        centerTitle: false,
      ),
      splashColor: AppColors.primaryBlue.withValues(alpha: 0.15),
      highlightColor: AppColors.primaryBlue.withValues(alpha: 0.08),
    );
  }

  static TextTheme _textTheme(TextTheme base) {
    return base
        .apply(
          bodyColor: AppColors.white,
          displayColor: AppColors.white,
          fontFamily: 'Roboto',
        )
        .copyWith(
          headlineLarge: base.headlineLarge?.copyWith(
            fontWeight: FontWeight.w800,
            letterSpacing: -0.5,
          ),
          headlineSmall: base.headlineSmall?.copyWith(
            fontWeight: FontWeight.w700,
          ),
          titleLarge: base.titleLarge?.copyWith(fontWeight: FontWeight.w700),
          titleMedium: base.titleMedium?.copyWith(fontWeight: FontWeight.w600),
          bodyMedium: base.bodyMedium?.copyWith(color: AppColors.lightGrey),
          labelLarge: base.labelLarge?.copyWith(fontWeight: FontWeight.w700),
        );
  }
}
