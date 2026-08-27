import 'package:flutter/material.dart';

import '../data/mock_data.dart';
import '../data/technician_repository.dart';
import '../models/models.dart';
import '../services/auth_service.dart';
import '../theme/app_colors.dart';
import '../widgets/common.dart';
import '../widgets/dashboard_widgets.dart';
import '../widgets/glass_card.dart';
import 'technician_detail_screen.dart';
import 'welcome_screen.dart';

/// Tableau de bord client : point d'entrée après la bienvenue.
class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  final TechnicianRepository _repository = const TechnicianRepository();
  late Future<List<Technician>> _technicians;

  @override
  void initState() {
    super.initState();
    _technicians = _repository.fetchNearby();
  }

  void _openTechnician(BuildContext context, Technician technician) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => TechnicianDetailScreen(technician: technician),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: DecoratedBox(
        decoration: const BoxDecoration(gradient: AppColors.backgroundGradient),
        child: SafeArea(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 32),
            children: [
              const _DashboardHeader(),
              const SizedBox(height: 22),
              const _SearchCard(),
              const SizedBox(height: 28),
              SectionHeader(title: 'Catégories', actionLabel: 'Voir tout →'),
              const SizedBox(height: 14),
              _CategoryGrid(
                onTap: (_) {},
              ),
              const SizedBox(height: 28),
              Text(
                'Statistiques',
                style: Theme.of(context)
                    .textTheme
                    .titleLarge
                    ?.copyWith(fontSize: 18),
              ),
              const SizedBox(height: 14),
              const _StatsGrid(),
              const SizedBox(height: 28),
              SectionHeader(
                title: '📍 Techniciens près de vous',
                actionLabel: 'Voir tout →',
                onAction: () {},
              ),
              const SizedBox(height: 14),
              FutureBuilder<List<Technician>>(
                future: _technicians,
                builder: (context, snapshot) {
                  final techs = snapshot.data ?? MockData.technicians;
                  return Column(
                    children: [
                      for (final tech in techs) ...[
                        TechnicianTile(
                          technician: tech,
                          onTap: () => _openTechnician(context, tech),
                        ),
                        const SizedBox(height: 12),
                      ],
                    ],
                  );
                },
              ),
              const SizedBox(height: 16),
              Text(
                'Mes contrats récents',
                style: Theme.of(context)
                    .textTheme
                    .titleLarge
                    ?.copyWith(fontSize: 18),
              ),
              const SizedBox(height: 14),
              for (final contract in MockData.recentContracts) ...[
                ContractCard(contract: contract),
                const SizedBox(height: 12),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

/// Salutation + notifications + avatar.
class _DashboardHeader extends StatelessWidget {
  const _DashboardHeader();

  String _displayName() {
    const auth = AuthService();
    final user = auth.currentUser;
    if (user == null) return 'Mamadou';
    final meta = user.userMetadata;
    final firstName = (meta?['first_name'] as String?)?.trim();
    if (firstName != null && firstName.isNotEmpty) return firstName;
    final fullName = (meta?['full_name'] as String?)?.trim();
    if (fullName != null && fullName.isNotEmpty) {
      return fullName.split(' ').first;
    }
    return 'Mamadou';
  }

  Future<void> _logout(BuildContext context) async {
    const auth = AuthService();
    await auth.signOut();
    if (!context.mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const WelcomeScreen()),
      (route) => false,
    );
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final name = _displayName();
    final initial = name.isNotEmpty ? name[0].toUpperCase() : 'M';
    return Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Bonjour $name 👋',
                style: textTheme.headlineSmall?.copyWith(fontSize: 22),
              ),
              const SizedBox(height: 4),
              Text(
                "Trouvez le technicien qu'il vous faut aujourd'hui.",
                style: textTheme.bodyMedium?.copyWith(
                  color: AppColors.lightGrey,
                  fontSize: 13.5,
                ),
              ),
            ],
          ),
        ),
        const SizedBox(width: 12),
        _CircleIconButton(icon: Icons.notifications_none_rounded, badge: true),
        const SizedBox(width: 12),
        PopupMenuButton<String>(
          tooltip: 'Compte',
          color: AppColors.card,
          onSelected: (value) {
            if (value == 'logout') _logout(context);
          },
          itemBuilder: (context) => const [
            PopupMenuItem<String>(
              value: 'logout',
              child: Row(
                children: [
                  Icon(Icons.logout_rounded,
                      color: AppColors.white, size: 18),
                  SizedBox(width: 10),
                  Text('Se déconnecter',
                      style: TextStyle(color: AppColors.white)),
                ],
              ),
            ),
          ],
          child: Container(
            width: 46,
            height: 46,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: AppColors.blueGradient,
              border: Border.all(color: AppColors.glassBorder),
            ),
            alignment: Alignment.center,
            child: Text(
              initial,
              style: const TextStyle(
                color: AppColors.white,
                fontWeight: FontWeight.w800,
                fontSize: 18,
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _CircleIconButton extends StatelessWidget {
  const _CircleIconButton({required this.icon, this.badge = false});

  final IconData icon;
  final bool badge;

  @override
  Widget build(BuildContext context) {
    return Stack(
      clipBehavior: Clip.none,
      children: [
        Container(
          width: 46,
          height: 46,
          decoration: BoxDecoration(
            color: AppColors.white.withOpacity( 0.06),
            shape: BoxShape.circle,
            border: Border.all(color: AppColors.glassBorder),
          ),
          child: Icon(icon, color: AppColors.white, size: 22),
        ),
        if (badge)
          Positioned(
            right: 10,
            top: 10,
            child: Container(
              width: 9,
              height: 9,
              decoration: BoxDecoration(
                color: AppColors.red,
                shape: BoxShape.circle,
                border: Border.all(color: AppColors.background, width: 1.5),
              ),
            ),
          ),
      ],
    );
  }
}

/// Grande carte à dégradé bleu : recherche d'un technicien.
class _SearchCard extends StatelessWidget {
  const _SearchCard();

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return GlassCard(
      gradient: AppColors.blueGradient,
      padding: const EdgeInsets.all(20),
      radius: 24,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '🔎 Trouver un technicien',
            style: textTheme.titleLarge?.copyWith(fontSize: 19),
          ),
          const SizedBox(height: 8),
          Text(
            'Des centaines de techniciens qualifiés près de chez vous à Conakry.',
            style: textTheme.bodyMedium?.copyWith(
              color: AppColors.white.withOpacity( 0.85),
              fontSize: 13.5,
              height: 1.4,
            ),
          ),
          const SizedBox(height: 18),
          _SearchField(),
          const SizedBox(height: 12),
          const _LocationDropdown(),
          const SizedBox(height: 16),
          GradientButton(
            label: 'Rechercher',
            gradient: AppColors.orangeGradient,
            trailingIcon: Icons.arrow_forward_rounded,
            height: 52,
            onPressed: () {},
          ),
        ],
      ),
    );
  }
}

class _SearchField extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return TextField(
      style: const TextStyle(color: AppColors.white),
      cursorColor: AppColors.orange,
      decoration: InputDecoration(
        isDense: true,
        filled: true,
        fillColor: AppColors.background.withOpacity( 0.55),
        hintText: 'Ex : plombier, électricien, frigoriste...',
        hintStyle: const TextStyle(color: AppColors.lightGrey, fontSize: 13.5),
        prefixIcon:
            const Icon(Icons.search, color: AppColors.lightGrey, size: 22),
        contentPadding: const EdgeInsets.symmetric(vertical: 14),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: BorderSide.none,
        ),
      ),
    );
  }
}

class _LocationDropdown extends StatefulWidget {
  const _LocationDropdown();

  @override
  State<_LocationDropdown> createState() => _LocationDropdownState();
}

class _LocationDropdownState extends State<_LocationDropdown> {
  static const _zones = [
    'Toute Conakry',
    'Kaloum',
    'Ratoma',
    'Matam',
    'Dixinn',
    'Matoto',
  ];
  String _value = _zones.first;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14),
      decoration: BoxDecoration(
        color: AppColors.background.withOpacity( 0.55),
        borderRadius: BorderRadius.circular(16),
      ),
      child: DropdownButtonHideUnderline(
        child: DropdownButton<String>(
          value: _value,
          isExpanded: true,
          dropdownColor: AppColors.card,
          borderRadius: BorderRadius.circular(16),
          icon: const Icon(Icons.keyboard_arrow_down_rounded,
              color: AppColors.lightGrey),
          style: const TextStyle(color: AppColors.white, fontSize: 14),
          items: [
            for (final zone in _zones)
              DropdownMenuItem(
                value: zone,
                child: Row(
                  children: [
                    const Icon(Icons.location_on_outlined,
                        color: AppColors.orange, size: 18),
                    const SizedBox(width: 8),
                    Text(zone),
                  ],
                ),
              ),
          ],
          onChanged: (v) => setState(() => _value = v ?? _value),
        ),
      ),
    );
  }
}

/// Grille 2 colonnes des catégories.
class _CategoryGrid extends StatelessWidget {
  const _CategoryGrid({required this.onTap});

  final ValueChanged<ServiceCategory> onTap;

  @override
  Widget build(BuildContext context) {
    return GridView.count(
      crossAxisCount: 2,
      mainAxisSpacing: 14,
      crossAxisSpacing: 14,
      childAspectRatio: 1.1,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      children: [
        for (final category in MockData.categories)
          CategoryCard(category: category, onTap: () => onTap(category)),
      ],
    );
  }
}

/// Grille 2 colonnes des statistiques.
class _StatsGrid extends StatelessWidget {
  const _StatsGrid();

  @override
  Widget build(BuildContext context) {
    return GridView.count(
      crossAxisCount: 2,
      mainAxisSpacing: 14,
      crossAxisSpacing: 14,
      childAspectRatio: 1.3,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      children: [
        for (final stat in MockData.stats) StatCard(stat: stat),
      ],
    );
  }
}
