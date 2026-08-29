import '../models/models.dart';
import '../services/api_service.dart';
import 'mock_data.dart';

/// Source de donnees des techniciens.
///
/// Interroge le backend Flask quand l'app est configuree ; retombe sur les
/// donnees de demo sinon ou en cas d'erreur, afin que l'interface reste
/// toujours fonctionnelle.
class TechnicianRepository {
  const TechnicianRepository();

  Future<List<Technician>> fetchNearby({int limit = 10}) async {
    if (ApiService.isConfigured) {
      try {
        final rows = await ApiService.getTechnicians();
        final list = rows.map(Technician.fromJson).take(limit).toList();
        if (list.isNotEmpty) return list;
      } catch (_) {}
    }
    return MockData.technicians;
  }
}
