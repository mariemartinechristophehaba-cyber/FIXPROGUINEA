import 'package:flutter/material.dart';

import '../models/models.dart';
import '../theme/app_colors.dart';
import '../widgets/common.dart';
import '../widgets/dashboard_widgets.dart';
import '../widgets/glass_card.dart';

/// Fiche détaillée d'un technicien : photo, identité, note, statistiques.
class TechnicianDetailScreen extends StatelessWidget {
  const TechnicianDetailScreen({super.key, required this.technician});

  final Technician technician;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Scaffold(
      body: DecoratedBox(
        decoration: const BoxDecoration(gradient: AppColors.backgroundGradient),
        child: SafeArea(
          child: Column(
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
                child: Row(
                  children: [
                    IconButton(
                      onPressed: () => Navigator.of(context).maybePop(),
                      icon: const Icon(Icons.arrow_back_ios_new_rounded,
                          color: AppColors.white, size: 20),
                    ),
                    Expanded(
                      child: Text(
                        'Profil du technicien',
                        style: textTheme.titleLarge?.copyWith(fontSize: 17),
                      ),
                    ),
                    IconButton(
                      onPressed: () {},
                      icon: const Icon(Icons.favorite_border_rounded,
                          color: AppColors.white, size: 22),
                    ),
                  ],
                ),
              ),
              Expanded(
                child: ListView(
                  padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
                  children: [
                    _ProfileHeader(technician: technician),
                    const SizedBox(height: 22),
                    _StatsRow(technician: technician),
                    const SizedBox(height: 22),
                    Text('À propos',
                        style: textTheme.titleLarge?.copyWith(fontSize: 17)),
                    const SizedBox(height: 10),
                    GlassCard(
                      child: Text(
                        technician.about,
                        style: textTheme.bodyMedium?.copyWith(
                          color: AppColors.lightGrey,
                          height: 1.5,
                          fontSize: 14,
                        ),
                      ),
                    ),
                    const SizedBox(height: 22),
                    _RateCard(technician: technician),
                  ],
                ),
              ),
              _BottomBar(technician: technician),
            ],
          ),
        ),
      ),
    );
  }
}

class _ProfileHeader extends StatelessWidget {
  const _ProfileHeader({required this.technician});

  final Technician technician;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Column(
      children: [
        TechnicianAvatar(technician: technician, size: 108, showBadge: true),
        const SizedBox(height: 16),
        Text(technician.name,
            style: textTheme.headlineSmall?.copyWith(fontSize: 24)),
        const SizedBox(height: 4),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(technician.icon, color: AppColors.orange, size: 18),
            const SizedBox(width: 6),
            Text(
              technician.job,
              style: const TextStyle(
                color: AppColors.lightGrey,
                fontSize: 15,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
          decoration: BoxDecoration(
            color: AppColors.orange.withOpacity( 0.14),
            borderRadius: BorderRadius.circular(20),
          ),
          child: RatingStars(rating: technician.rating, size: 18),
        ),
      ],
    );
  }
}

class _StatsRow extends StatelessWidget {
  const _StatsRow({required this.technician});

  final Technician technician;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: _MiniStat(
            value: technician.rating.toStringAsFixed(1),
            label: 'Note',
            icon: Icons.star_rounded,
            color: AppColors.orange,
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _MiniStat(
            value: '${technician.reviewCount}',
            label: 'Avis',
            icon: Icons.reviews_rounded,
            color: AppColors.primaryBlue,
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _MiniStat(
            value: '${technician.interventions}',
            label: 'Interventions',
            icon: Icons.handyman_rounded,
            color: AppColors.green,
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _MiniStat(
            value: '${technician.experienceYears} ans',
            label: 'Expérience',
            icon: Icons.workspace_premium_rounded,
            color: AppColors.red,
          ),
        ),
      ],
    );
  }
}

class _MiniStat extends StatelessWidget {
  const _MiniStat({
    required this.value,
    required this.label,
    required this.icon,
    required this.color,
  });

  final String value;
  final String label;
  final IconData icon;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return GlassCard(
      color: AppColors.cardDeep,
      padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 6),
      child: Column(
        children: [
          Icon(icon, color: color, size: 22),
          const SizedBox(height: 8),
          FittedBox(
            child: Text(
              value,
              style: const TextStyle(
                color: AppColors.white,
                fontWeight: FontWeight.w800,
                fontSize: 16,
              ),
            ),
          ),
          const SizedBox(height: 2),
          Text(
            label,
            textAlign: TextAlign.center,
            style: const TextStyle(color: AppColors.lightGrey, fontSize: 10.5),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
    );
  }
}

class _RateCard extends StatelessWidget {
  const _RateCard({required this.technician});

  final Technician technician;

  @override
  Widget build(BuildContext context) {
    return GlassCard(
      gradient: AppColors.blueGradient,
      child: Row(
        children: [
          const Icon(Icons.payments_rounded, color: AppColors.white, size: 28),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Tarif horaire',
                  style: TextStyle(color: Colors.white70, fontSize: 13),
                ),
                const SizedBox(height: 4),
                Text(
                  '${formatGnf(technician.hourlyRate)} GNF / heure',
                  style: const TextStyle(
                    color: AppColors.white,
                    fontWeight: FontWeight.w800,
                    fontSize: 18,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _BottomBar extends StatelessWidget {
  const _BottomBar({required this.technician});

  final Technician technician;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(20, 14, 20, 20),
      decoration: BoxDecoration(
        color: AppColors.cardDeep,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity( 0.3),
            blurRadius: 20,
            offset: const Offset(0, -6),
          ),
        ],
      ),
      child: Row(
        children: [
          _CircleAction(icon: Icons.call_rounded, onTap: () {}),
          const SizedBox(width: 12),
          _CircleAction(icon: Icons.chat_bubble_outline_rounded, onTap: () {}),
          const SizedBox(width: 16),
          Expanded(
            child: GradientButton(
              label: 'Réserver maintenant',
              gradient: AppColors.orangeGradient,
              onPressed: () {},
            ),
          ),
        ],
      ),
    );
  }
}

class _CircleAction extends StatelessWidget {
  const _CircleAction({required this.icon, required this.onTap});

  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.primaryBlue.withOpacity( 0.18),
      shape: const CircleBorder(),
      child: InkWell(
        customBorder: const CircleBorder(),
        onTap: onTap,
        child: SizedBox(
          width: 52,
          height: 52,
          child: Icon(icon, color: AppColors.primaryBlue, size: 24),
        ),
      ),
    );
  }
}
