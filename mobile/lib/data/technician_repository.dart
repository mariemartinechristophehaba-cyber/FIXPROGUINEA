import '../models/models.dart';
import '../services/supabase_service.dart';
import 'mock_data.dart';

/// Source de données des techniciens.
///
/// Interroge Supabase (table `profiles`, rôles artisan/technicien) quand
/// l'app est configurée ; retombe sur les données de démo sinon ou en cas
/// d'erreur, afin que l'interface reste toujours fonctionnelle.
class TechnicianRepository {
  const TechnicianRepository();

  static const List<String> _artisanRoles = [
    'artisan',
    'technicien',
    'technician',
    'prestataire',
  ];

  Future<List<Technician>> fetchNearby({int limit = 10}) async {
    if (!SupabaseService.isReady) return MockData.technicians;
    try {
      final rows = await SupabaseService.client
          .from('profiles')
          .select()
          .inFilter('role', _artisanRoles)
          .limit(limit);
      final list = (rows as List)
          .cast<Map<String, dynamic>>()
          .map(Technician.fromProfile)
          .toList();
      return list.isEmpty ? MockData.technicians : list;
    } catch (_) {
      return MockData.technicians;
    }
  }
}
