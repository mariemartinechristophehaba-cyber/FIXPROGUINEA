import 'package:flutter/material.dart';

/// Palette de couleurs FixPro (Dark Mode premium).
class AppColors {
  AppColors._();

  /// Fond principal de l'application.
  static const Color background = Color(0xFF071A33);

  /// Bleu principal (actions, accents).
  static const Color primaryBlue = Color(0xFF2E5BFF);

  /// Bleu secondaire (dégradés, surfaces).
  static const Color secondaryBlue = Color(0xFF163B8C);

  /// Orange (call-to-action principal).
  static const Color orange = Color(0xFFF5A623);

  /// Vert (succès, statut "terminé").
  static const Color green = Color(0xFF28C76F);

  /// Rouge (erreurs, alertes).
  static const Color red = Color(0xFFEA5455);

  /// Blanc pur (texte principal sur fond sombre).
  static const Color white = Color(0xFFFFFFFF);

  /// Gris clair (texte secondaire).
  static const Color lightGrey = Color(0xFFAAB2C8);

  /// Surface des cartes sur fond sombre.
  static const Color card = Color(0xFF0E2647);

  /// Surface plus profonde (cartes catégories).
  static const Color cardDeep = Color(0xFF0A1F3D);

  /// Bordure subtile pour l'effet glassmorphism.
  static const Color glassBorder = Color(0x1AFFFFFF);

  /// Dégradé bleu principal (carte de recherche, boutons).
  static const LinearGradient blueGradient = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [primaryBlue, secondaryBlue],
  );

  /// Dégradé orange (bouton "Rechercher").
  static const LinearGradient orangeGradient = LinearGradient(
    begin: Alignment.centerLeft,
    end: Alignment.centerRight,
    colors: [Color(0xFFF7B84B), orange],
  );

  /// Dégradé de fond global (subtil).
  static const LinearGradient backgroundGradient = LinearGradient(
    begin: Alignment.topCenter,
    end: Alignment.bottomCenter,
    colors: [Color(0xFF0A1F3D), background],
  );
}
