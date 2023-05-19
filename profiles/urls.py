from django.urls import path
 
from .views import BusinessView, UserView

urlpatterns = [
    path('busniess/<int:id>/', BusinessView.as_view(), name='business'),
    path('user/<int:id>/', UserView.as_view(), name='user'),
]