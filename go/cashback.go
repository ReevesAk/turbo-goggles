package main

import (
	"encoding/json"
	"log"
	"net/http"
)

type CashbackRequest struct {
	Amount float64 `json:"amount"`
	Rate   float64 `json:"rate"`
}

type CashbackResponse struct {
	Cashback float64 `json:"cashback"`
}

func calculateCashback(amount, rate float64) float64 {
	return amount * rate
}

func cashbackHandler(w http.ResponseWriter, r *http.Request) {
	var req CashbackRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request", http.StatusBadRequest)
		return
	}
	cashback := calculateCashback(req.Amount, req.Rate)
	resp := CashbackResponse{Cashback: cashback}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(resp)
}

func main() {
	http.HandleFunc("/cashback", cashbackHandler)
	log.Println("Go Cashback service running on :8081")
	log.Fatal(http.ListenAndServe(":8081", nil))
}
