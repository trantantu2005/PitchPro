"""Legacy URL include retained for older integrations."""
from django.urls import include, path

urlpatterns = [
    path('', include('process_1.urls')),
    path('', include('process_2.urls')),
]
