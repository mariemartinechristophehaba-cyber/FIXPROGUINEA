import 'package:flutter/material.dart';

import '../models/models.dart';
import '../theme/app_colors.dart';
import 'common.dart';
import 'glass_card.dart';

/// Avatar rond avec initiales et badge du métier.
class TechnicianAvatar extends StatelessWidget {
  const TechnicianAvatar({
    super.key,
    required this.technician,
    this.size = 52,
    this.showBadge = true,
  });

  final Technician technician;
  final double size;
  final bool showBadge;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: size,
      height: size,
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          Container(
            width: size,
            height: size,
            decoration: const BoxDecoration(
              shape: BoxShape.circle,
              gradient: AppColors.blueGradient,
            ),
            alignment: Alignment.center,
            child: Text(
              technician.initials,
              style: TextStyle(
                color: AppColors.white,
                fontWeight: FontWeight.w800,
                fontSize: size * 0.34,
              ),
            ),
          ),
          if (showBadge)
            Positioned(
              right: -2,
              bottom: -2,
              child: Container(
                padding: const EdgeInsets.all(5),
                decoration: BoxDecoration(
                  color: AppColors.orange,
                  shape: BoxShape.circle,
                  border: Border.all(color: AppColors.background, width: 2),
                ),
                child: Icon(technician.icon,
                    color: AppColors.white, size: size * 0.24),
              ),
            ),
        ],
      ),
    );
  }
}

/// Carte de catégorie (grille 2 colonnes) avec animation d'appui.
class CategoryCard extends StatefulWidget {
  const CategoryCard({super.key, required this.category, this.onTap});

  final ServiceCategory category;
  final VoidCallback? onTap;

  @override
  State<CategoryCard> createState() => _CategoryCardState();
}

class _CategoryCardState extends State<CategoryCard> {
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTapDown: (_) => setState(() => _pressed = true),
      onTapUp: (_) => setState(() => _pressed = false),
      onTapCancel: () => setState(() => _pressed = false),
      onTap: widget.onTap,
      child: AnimatedScale(
        scale: _pressed ? 0.96 : 1,
        duration: const Duration(milliseconds: 120),
        child: GlassCard(
          color: AppColors.cardDeep,
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: AppColors.primaryBlue.withOpacity( 0.18),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Icon(widget.category.icon,
                    color: AppColors.primaryBlue, size: 24),
              ),
              const SizedBox(height: 12),
              Text(
                '${widget.category.emoji} ${widget.category.label}',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context)
                    .textTheme
                    .titleMedium
                    ?.copyWith(fontSize: 15),
              ),
              const SizedBox(height: 4),
              Text(
                '${widget.category.technicianCount} techniciens',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                    color: AppColors.lightGrey, fontSize: 12.5),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Carte de statistique.
class StatCard extends StatelessWidget {
  const StatCard({super.key, required this.stat});

  final DashboardStat stat;

  @override
  Widget build(BuildContext context) {
    return GlassCard(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(stat.emoji, style: const TextStyle(fontSize: 18)),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  stat.title,
                  style: const TextStyle(
                      color: AppColors.lightGrey, fontSize: 12.5),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            stat.value,
            style: Theme.of(context)
                .textTheme
                .headlineSmall
                ?.copyWith(fontSize: 24, color: stat.accent),
          ),
          const SizedBox(height: 6),
          Text(
            stat.trend,
            style: const TextStyle(color: AppColors.lightGrey, fontSize: 11.5),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
    );
  }
}

/// Ligne d'un technicien dans la liste "près de vous".
class TechnicianTile extends StatelessWidget {
  const TechnicianTile({super.key, required this.technician, this.onTap});

  final Technician technician;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return GlassCard(
      onTap: onTap,
      padding: const EdgeInsets.all(14),
      child: Row(
        children: [
          TechnicianAvatar(technician: technician),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  technician.name,
                  style: Theme.of(context)
                      .textTheme
                      .titleMedium
                      ?.copyWith(fontSize: 15.5),
                ),
                const SizedBox(height: 2),
                Text(
                  technician.job,
                  style: const TextStyle(
                      color: AppColors.lightGrey, fontSize: 13),
                ),
                const SizedBox(height: 6),
                FittedBox(
                  fit: BoxFit.scaleDown,
                  alignment: Alignment.centerLeft,
                  child: Row(
                    children: [
                      RatingStars(rating: technician.rating, size: 13),
                      const SizedBox(width: 10),
                      const Icon(Icons.location_on,
                          color: AppColors.lightGrey, size: 13),
                      const SizedBox(width: 2),
                      Text(
                        '${technician.distanceKm.toStringAsFixed(1)} km',
                        style: const TextStyle(
                            color: AppColors.lightGrey, fontSize: 12.5),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                '${formatGnf(technician.hourlyRate)} GNF',
                style: const TextStyle(
                  color: AppColors.orange,
                  fontWeight: FontWeight.w800,
                  fontSize: 14,
                ),
              ),
              const Text('/heure',
                  style: TextStyle(color: AppColors.lightGrey, fontSize: 11)),
            ],
          ),
        ],
      ),
    );
  }
}

/// Carte d'un contrat récent avec badge de statut coloré.
class ContractCard extends StatelessWidget {
  const ContractCard({super.key, required this.contract});

  final Contract contract;

  @override
  Widget build(BuildContext context) {
    return GlassCard(
      padding: const EdgeInsets.all(16),
      child: Row(
        children: [
          Container(
            width: 4,
            height: 46,
            decoration: BoxDecoration(
              color: contract.status.color,
              borderRadius: BorderRadius.circular(4),
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  contract.title,
                  style: Theme.of(context)
                      .textTheme
                      .titleMedium
                      ?.copyWith(fontSize: 15),
                ),
                const SizedBox(height: 3),
                Text(
                  '${contract.technicianName} • ${contract.date}',
                  style: const TextStyle(
                      color: AppColors.lightGrey, fontSize: 12.5),
                ),
              ],
            ),
          ),
          const SizedBox(width: 10),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                contract.amount,
                style: const TextStyle(
                  color: AppColors.white,
                  fontWeight: FontWeight.w700,
                  fontSize: 14,
                ),
              ),
              const SizedBox(height: 6),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: contract.status.color.withOpacity( 0.16),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  '${contract.status.emoji} ${contract.status.label}',
                  style: TextStyle(
                    color: contract.status.color,
                    fontWeight: FontWeight.w700,
                    fontSize: 11.5,
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
